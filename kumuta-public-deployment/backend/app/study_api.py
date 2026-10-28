"""Owner/project-scoped learning routes using existing authentication."""
import json
from typing import Literal
from fastapi import Depends, HTTPException, Query
from pydantic import create_model
from sqlalchemy import select
from sqlalchemy.orm import Session
from fsrs import Card as FSRSCard, Rating
from . import study as s, study_models as m, study_schemas as schema, workspaces as ws
from .database import User, now
from starlette.concurrency import run_in_threadpool
from . import study_generation

REGISTRY = {'courses': (m.Course, schema.CourseData), 'chapters': (m.Chapter, schema.ChapterData),
    'lessons': (m.Lesson, schema.LessonData), 'resources': (m.Resource, schema.ResourceData),
    'quizzes': (m.Quiz, schema.QuizData), 'decks': (m.Deck, schema.DeckData),
    'cards': (m.Card, schema.CardData), 'plans': (m.Plan, schema.PlanData)}


def register(app, auth, session):
    def project(pid, user, db, write=False):
        if write: ws.lock_writes(user, db)
        return ws.owned_project(pid, user, db, writable=write)

    @app.post('/projects/{pid}/study/draft')
    async def draft(pid: int, data: schema.CourseRequest, user: User = Depends(auth), db: Session = Depends(session)):
        project(pid, user, db)
        ws.owned_project(pid, user, db, writable=True)
        source = None
        if data.source != 'topic' and not data.confirm_source:
            raise HTTPException(422, 'Confirm sending the selected source excerpt to your model.')
        if data.source == 'document':
            source = study_generation.document_source(pid, data.document_id, user, db)
        db.commit()
        if data.source == 'url': source = await run_in_threadpool(study_generation.url_source, data.url)
        result = await study_generation.generate(data, source, user)
        db.expire_all(); ws.owned_project(pid, user, db, writable=True)
        if data.source == 'document': study_generation.document_source(pid, data.document_id, user, db)
        return result

    @app.post('/projects/{pid}/study/outline', status_code=201)
    def save_outline(pid: int, data: schema.SaveOutline, user: User = Depends(auth), db: Session = Depends(session)):
        project(pid, user, db, True)
        source = study_generation.document_source(pid, data.document_id, user, db) if data.document_id else None
        if data.url: study_generation.wikipedia_title(data.url)
        outline = data.outline
        row = m.Course(owner_id=user.id, project_id=pid, **outline.model_dump(exclude={'chapters'}))
        db.add(row); db.flush()
        for i, chapter in enumerate(outline.chapters):
            parent = m.Chapter(owner_id=user.id, project_id=pid, course_id=row.id, title=chapter.title, position=(i+1)*1024)
            db.add(parent); db.flush()
            for j, lesson in enumerate(chapter.lessons):
                db.add(m.Lesson(owner_id=user.id, project_id=pid, course_id=row.id, chapter_id=parent.id,
                    title=lesson.title, content=lesson.content, origin=outline.origin, position=(j+1)*1024))
        if source or data.url:
            db.add(m.Resource(owner_id=user.id, project_id=pid, course_id=row.id,
                title=source['title'] if source else study_generation.wikipedia_title(data.url).replace('_', ' '),
                document_id=data.document_id, url=data.url))
        db.commit()
        return s.view(row, db)

    def routes(kind, model, data_schema):
        edit_schema = create_model(f'{data_schema.__name__}Edit', __base__=data_schema, revision=(int, schema.Field(ge=1)))
        path = f'/projects/{{pid}}/study/{kind}'

        @app.get(path, name=f'list_study_{kind}')
        def listing(pid: int, q: str = Query('', max_length=200), course_id: int | None = None,
                    deck_id: int | None = None, due: bool = False, archived: bool | None = None,
                    completed: bool | None = None, sort: Literal['position','updated'] = 'position',
                    limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0),
                    user: User = Depends(auth), db: Session = Depends(session)):
            project(pid, user, db)
            query = select(model).where(model.project_id == pid, model.owner_id == user.id)
            if q.strip(): query = query.where(getattr(model, 'title', getattr(model, 'front', None)).icontains(q.strip(), autoescape=True))
            if course_id is not None:
                s.owned(m.Course, course_id, pid, user, db)
                if hasattr(model, 'course_id'): query = query.where(model.course_id == course_id)
            if deck_id is not None:
                s.owned(m.Deck, deck_id, pid, user, db)
                if hasattr(model, 'deck_id'): query = query.where(model.deck_id == deck_id)
            if due and model is m.Card: query = query.where(m.Card.due_at <= now())
            if archived is not None and model is m.Course: query = query.where(m.Course.archived == archived)
            order = [model.position, model.id] if hasattr(model, 'position') else [model.id]
            if completed is not None and model is m.Lesson: query = query.where(m.Lesson.completed == completed)
            if sort == 'updated': order = [model.updated_at.desc(), model.id.desc()]
            rows = list(db.scalars(query.order_by(*order).offset(offset).limit(limit + 1)))
            return {'items': [s.view(x, db) for x in rows[:limit]], 'has_more': len(rows) > limit}

        @app.post(path, status_code=201, name=f'create_study_{kind}')
        def create(pid: int, data: data_schema, user: User = Depends(auth), db: Session = Depends(session)):
            project(pid, user, db, True)
            row = model(owner_id=user.id, project_id=pid)
            if hasattr(model, 'position'):
                conditions = [model.project_id == pid]
                conditions.append(model.chapter_id == data.chapter_id if model is m.Lesson else model.course_id == data.course_id)
                row.position = ws.next_position(model, conditions, db)
            if model is m.Card: row.schedule = FSRSCard().to_json()
            # Validate references before flushing a new row.
            if model is m.Plan:
                row.title = data.title; db.add(row)
            s.apply(row, data, pid, user, db)
            db.add(row); db.commit()
            return s.view(row, db)

        @app.get(path + '/{identity}', name=f'get_study_{kind}')
        def get(pid: int, identity: int, user: User = Depends(auth), db: Session = Depends(session)):
            project(pid, user, db)
            return s.view(s.owned(model, identity, pid, user, db), db)

        @app.put(path + '/{identity}', name=f'edit_study_{kind}')
        def edit(pid: int, identity: int, data: edit_schema, user: User = Depends(auth), db: Session = Depends(session)):
            project(pid, user, db, True)
            row = s.owned(model, identity, pid, user, db); ws.check_revision(row, data.revision)
            s.apply(row, data, pid, user, db); ws.touch(row); db.commit()
            return s.view(row, db)

        @app.delete(path + '/{identity}', name=f'delete_study_{kind}')
        def remove(pid: int, identity: int, data: schema.Revision, user: User = Depends(auth), db: Session = Depends(session)):
            project(pid, user, db, True)
            row = s.owned(model, identity, pid, user, db); ws.check_revision(row, data.revision)
            db.delete(row); db.commit(); return {'ok': True}

    for kind, (model, data_schema) in REGISTRY.items(): routes(kind, model, data_schema)

    @app.post('/projects/{pid}/study/{kind}/{identity}/move')
    def move(pid: int, kind: str, identity: int, data: schema.Move, user: User = Depends(auth), db: Session = Depends(session)):
        project(pid, user, db, True)
        model = {'chapters': m.Chapter, 'lessons': m.Lesson}.get(kind)
        if model is None: raise HTTPException(404, 'This resource cannot be reordered')
        row = s.owned(model, identity, pid, user, db); ws.check_revision(row, data.revision)
        conditions = [model.project_id == pid, model.owner_id == user.id,
            model.chapter_id == row.chapter_id if model is m.Lesson else model.course_id == row.course_id]
        ws.place(model, row, conditions, data.before_id, db); ws.touch(row); db.commit()
        return s.view(row, db)

    @app.post('/projects/{pid}/study/quizzes/{identity}/attempts', status_code=201)
    def submit(pid: int, identity: int, data: schema.Submission, user: User = Depends(auth), db: Session = Depends(session)):
        project(pid, user, db, True)
        quiz = s.owned(m.Quiz, identity, pid, user, db); ws.check_revision(quiz, data.revision)
        if not quiz.published: raise HTTPException(409, 'Publish this quiz before attempting it.')
        result = s.score(quiz, data)
        row = m.Attempt(owner_id=user.id, project_id=pid, quiz_id=identity, quiz_revision=quiz.revision,
                        score=sum(x['correct'] for x in result), total=len(result), result=json.dumps(result))
        db.add(row); db.commit(); return s.view(row, db)

    @app.post('/projects/{pid}/study/cards/{identity}/review', status_code=201)
    def review(pid: int, identity: int, data: schema.Rating, user: User = Depends(auth), db: Session = Depends(session)):
        project(pid, user, db, True)
        row = s.owned(m.Card, identity, pid, user, db); ws.check_revision(row, data.revision)
        if row.due_at > now(): raise HTTPException(409, 'This card is not due yet. Refresh your review queue.')
        card, log = s.SCHEDULER.review_card(FSRSCard.from_json(row.schedule), Rating(data.rating))
        row.schedule, row.due_at, row.reviews = card.to_json(), card.due.isoformat(), row.reviews + 1
        ws.touch(row)
        db.add(m.Review(owner_id=user.id, project_id=pid, card_id=identity, rating=data.rating,
                        log=log.to_json(), due_at=row.due_at)); db.commit(); return s.view(row, db)

    def history_routes(kind, model, field):
        @app.get(f'/projects/{{pid}}/study/{kind}')
        def history(pid: int, identity: int = Query(gt=0), limit: int = Query(100, ge=1, le=200),
                    offset: int = Query(0, ge=0), user: User = Depends(auth), db: Session = Depends(session)):
            project(pid, user, db)
            s.owned(m.Quiz if model is m.Attempt else m.Card, identity, pid, user, db)
            rows = list(db.scalars(select(model).where(model.project_id == pid, model.owner_id == user.id,
                getattr(model, field) == identity).order_by(model.id.desc()).offset(offset).limit(limit + 1)))
            return {'items': [s.view(x, db) for x in rows[:limit]], 'has_more': len(rows) > limit}
    history_routes('attempts', m.Attempt, 'quiz_id'); history_routes('reviews', m.Review, 'card_id')
