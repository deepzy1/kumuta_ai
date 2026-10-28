"""Owner-authorized SQLite reports. Current snapshots and bounded activity stay distinct."""
import csv
import io
import json
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import Integer, case, func, select

from . import focus, focus_models as f, study_models as s, workspaces as ws
from .workspace_models import Project, Task, Workspace
from .progress import percentage, mean_progress, goal_progress
from .time_accounting import allocate

UTC = timezone.utc


def window(preset, start, end, tz, instant):
    tz = {'Asia/Calcutta': 'Asia/Kolkata', 'Asia/Katmandu': 'Asia/Kathmandu'}.get(tz, tz)
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(422, 'Unknown timezone') from None
    today = instant.astimezone(zone).date()
    if preset == 'custom':
        if start is None or end is None:
            raise HTTPException(422, 'Custom reports require start and end dates.')
    else:
        if start is not None or end is not None:
            raise HTTPException(422, 'Use the custom preset with explicit dates.')
        end = today
        start = today - timedelta(days={'today': 0, '7d': 6, '30d': 29}[preset])
    if end < start or (end - start).days >= 366:
        raise HTTPException(422, 'Choose an inclusive range of 1 to 366 days.')
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    try:
        boundaries = [datetime.combine(d, time.min, zone).astimezone(UTC) for d in days + [end + timedelta(days=1)]]
    except (OverflowError, ValueError):
        raise HTTPException(422, 'Date range is outside supported calendar boundaries.') from None
    return zone, days, boundaries


def authorized_projects(user, db, workspace_id, project_id, course_id):
    query = select(Project.id).where(Project.owner_id == user.id)
    if workspace_id is not None:
        if db.scalar(select(Workspace.id).where(Workspace.id == workspace_id, Workspace.owner_id == user.id)) is None:
            raise HTTPException(404, 'Workspace not found')
        query = query.where(Project.workspace_id == workspace_id)
    if project_id is not None:
        project = ws.owned_project(project_id, user, db)
        if workspace_id is not None and project.workspace_id != workspace_id:
            raise HTTPException(404, 'Project not found in this workspace')
        query = query.where(Project.id == project_id)
    if course_id is not None:
        course = db.scalar(select(s.Course).where(s.Course.id == course_id, s.Course.owner_id == user.id,
                                                 s.Course.project_id.in_(query)))
        if course is None:
            raise HTTPException(404, 'Course not found in this report scope')
        query = query.where(Project.id == course.project_id)
    return query


def report(user, db, *, preset='30d', start=None, end=None, tz='UTC', workspace_id=None,
           project_id=None, course_id=None, limit=50, offset=0):
    instant = focus.clock()
    zone, days, boundaries = window(preset, start, end, tz, instant)
    pids = authorized_projects(user, db, workspace_id, project_id, course_id)
    # Finalize expired timers through the existing state machine, once only.
    ws.lock_writes(user, db)
    focus.settle(user, db, instant)
    db.commit()
    # A consistent read snapshot across all aggregates (SQLite default legacy
    # transaction mode does not BEGIN on SELECT).
    db.connection().exec_driver_sql('BEGIN')
    lo, hi = focus.stamp(boundaries[0]), focus.stamp(boundaries[-1])
    daily = {d.isoformat(): {'date': d.isoformat(), 'lessons': 0, 'quiz_attempts': 0,
                            'reviews': 0, 'tasks': 0, 'focus_seconds': 0} for d in days}

    def scoped(model):
        conditions = [model.project_id.in_(pids)]
        if hasattr(model, 'owner_id'):
            conditions.append(model.owner_id == user.id)
        return conditions

    cids = select(s.Course.id).where(*scoped(s.Course))
    if course_id is not None:
        cids = cids.where(s.Course.id == course_id)
    lesson_scope = [*scoped(s.Lesson), s.Lesson.course_id.in_(cids)]
    quiz_ids = select(s.Quiz.id).where(*scoped(s.Quiz), s.Quiz.course_id.in_(cids))
    deck_ids = select(s.Deck.id).where(*scoped(s.Deck), s.Deck.course_id.in_(cids))
    card_ids = select(s.Card.id).where(*scoped(s.Card), s.Card.deck_id.in_(deck_ids))
    attempts_scope = [*scoped(s.Attempt), s.Attempt.quiz_id.in_(quiz_ids)]
    review_scope = [*scoped(s.Review), s.Review.card_id.in_(card_ids)]

    def activity(model, field, conditions, key):
        bucket = case(*[(field < focus.stamp(boundaries[i + 1]), days[i].isoformat()) for i in range(len(days))])
        query = select(bucket.label('day'), func.count()).where(*conditions, field >= lo, field < hi).group_by('day')
        for day, count in db.execute(query):
            daily[day][key] = count

    activity(s.Lesson, s.Lesson.completed_at, lesson_scope, 'lessons')
    activity(s.Attempt, s.Attempt.created_at, attempts_scope, 'quiz_attempts')
    activity(s.Review, s.Review.created_at, review_scope, 'reviews')
    activity(Task, Task.completed_at, scoped(Task), 'tasks')

    lesson_groups = select(s.Lesson.course_id.label('cid'), func.count().label('total'),
                           func.sum(s.Lesson.completed.cast(Integer)).label('done')).where(*lesson_scope).group_by(s.Lesson.course_id).subquery()
    total_lessons, done_lessons = db.execute(select(func.coalesce(func.sum(lesson_groups.c.total), 0),
                                                          func.coalesce(func.sum(lesson_groups.c.done), 0))).one()
    course_query = select(s.Course.id, s.Course.project_id, s.Course.title, s.Course.archived,
                          func.coalesce(lesson_groups.c.total, 0), func.coalesce(lesson_groups.c.done, 0)).outerjoin(
                              lesson_groups, lesson_groups.c.cid == s.Course.id).where(s.Course.id.in_(cids)).order_by(s.Course.id)
    courses = [{'id': cid, 'project_id': pid, 'title': title, 'archived': archived, 'lessons': total,
                'completed': done, 'progress': percentage(done, total, None)}
               for cid, pid, title, archived, total, done in db.execute(course_query.offset(offset).limit(limit + 1))]
    all_progress = {
        cid: percentage(done or 0, total or 0)
        for cid, total, done in db.execute(select(s.Course.id, lesson_groups.c.total, lesson_groups.c.done)
            .outerjoin(lesson_groups, lesson_groups.c.cid == s.Course.id).where(s.Course.id.in_(cids)))
    }
    quiz_query = select(s.Quiz.course_id, func.count(), func.avg(100.0 * s.Attempt.score / func.nullif(s.Attempt.total, 0))).join(
        s.Attempt, s.Attempt.quiz_id == s.Quiz.id).where(*attempts_scope, s.Attempt.created_at >= lo,
                                                      s.Attempt.created_at < hi).group_by(s.Quiz.course_id)
    quiz_per_course = [{'course_id': cid, 'attempts': count, 'average_score': round(avg, 2) if avg is not None else None}
                       for cid, count, avg in db.execute(quiz_query.offset(offset).limit(limit + 1))]
    attempt_count, average_score = db.execute(select(func.count(), func.avg(100.0 * s.Attempt.score / func.nullif(s.Attempt.total, 0))).where(
        *attempts_scope, s.Attempt.created_at >= lo, s.Attempt.created_at < hi)).one()
    ratings = dict(db.execute(select(s.Review.rating, func.count()).where(*review_scope, s.Review.created_at >= lo,
                                                                        s.Review.created_at < hi).group_by(s.Review.rating)).all())
    due = db.scalar(select(func.count()).select_from(s.Card).where(s.Card.id.in_(card_ids), s.Card.due_at <= focus.stamp(instant)))
    task_total, task_done = db.execute(select(func.count(), func.coalesce(func.sum(Task.completed.cast(Integer)), 0)).where(*scoped(Task))).one()
    task_states = dict(db.execute(select(Task.id, Task.completed).where(*scoped(Task))).all())
    upcoming_tasks = [{'id': tid, 'title': title, 'due_date': due_date, 'project_id': pid} for tid, title, due_date, pid in db.execute(
        select(Task.id, Task.title, Task.due_date, Task.project_id).where(*scoped(Task), Task.completed.is_(False), Task.due_date.is_not(None)).order_by(Task.due_date, Task.id).offset(offset).limit(limit + 1))]

    plan_query = select(s.Plan).where(*scoped(s.Plan))
    if course_id is not None:
        plan_query = plan_query.where(s.Plan.id.in_(select(s.PlanCourse.plan_id).where(s.PlanCourse.course_id == course_id)))
    plan_rows = list(db.scalars(plan_query.order_by(s.Plan.id).offset(offset).limit(limit + 1)))
    plan_ids = [x.id for x in plan_rows]
    plan_courses, plan_tasks = {}, {}
    for pid, cid in db.execute(select(s.PlanCourse.plan_id, s.PlanCourse.course_id).where(s.PlanCourse.plan_id.in_(plan_ids))):
        plan_courses.setdefault(pid, []).append(cid)
    # A course-filtered plan uses ALL its authorized linked courses, matching Study CRUD progress.
    missing = {cid for values in plan_courses.values() for cid in values} - all_progress.keys()
    if missing:
        for cid, total, done in db.execute(select(s.Lesson.course_id, func.count(), func.sum(s.Lesson.completed.cast(Integer))).where(
            *scoped(s.Lesson), s.Lesson.course_id.in_(missing)).group_by(s.Lesson.course_id)):
            all_progress[cid] = percentage(done, total)
    for pid, tid in db.execute(select(s.PlanTask.plan_id, s.PlanTask.task_id).where(s.PlanTask.plan_id.in_(plan_ids))):
        plan_tasks.setdefault(pid, []).append(tid)
    plans, milestones, upcoming_study = [], [], []
    planned_minutes = 0
    for row in plan_rows[:limit]:
        ms, sessions = json.loads(row.milestones), json.loads(row.sessions)
        values = [100 if x['completed'] else 0 for x in ms + sessions]
        values += [all_progress.get(cid, 0) for cid in plan_courses.get(row.id, [])]
        values += [100 if task_states[tid] else 0 for tid in plan_tasks.get(row.id, []) if tid in task_states]
        plans.append({'id': row.id, 'title': row.title, 'target_date': row.target_date, 'progress': mean_progress(values),
                      'milestones': len(ms), 'completed_milestones': sum(x['completed'] for x in ms)})
        milestones.extend({'source': 'study', 'parent': row.title, **x} for x in ms)
        for item in sessions:
            stamp = focus.dt(item['starts_at']).astimezone(UTC)
            if boundaries[0] <= stamp < boundaries[-1]:
                if item['completed']:
                    planned_minutes += item['minutes']
                elif stamp >= instant:
                    upcoming_study.append({'plan_id': row.id, **item})

    goal_rows = list(db.scalars(select(f.Goal).where(*scoped(f.Goal)).order_by(f.Goal.id).offset(offset).limit(limit + 1)))
    goal_tasks = {}
    for gid, tid in db.execute(select(f.GoalTask.goal_id, f.GoalTask.task_id).where(f.GoalTask.goal_id.in_([x.id for x in goal_rows]))):
        goal_tasks.setdefault(gid, []).append(tid)
    goals = []
    for row in goal_rows[:limit]:
        ms = json.loads(row.milestones)
        goals.append({'id': row.id, 'title': row.title, 'status': row.status,
                      'progress': goal_progress(ms, [task_states[tid] for tid in goal_tasks.get(row.id, []) if tid in task_states], row.status),
                      'milestones': len(ms), 'completed_milestones': sum(x['completed'] for x in ms)})
        milestones.extend({'source': 'focus', 'parent': row.title, **x} for x in ms)

    distribution, estimated = {}, False
    entries = select(f.TimeEntry).where(*scoped(f.TimeEntry), f.TimeEntry.ended_at > lo, f.TimeEntry.started_at < hi)
    for row in db.scalars(entries.execution_options(yield_per=500)):
        values, approximation = allocate(row, boundaries)
        estimated |= approximation
        for day, seconds in zip(days, values):
            daily[day.isoformat()]['focus_seconds'] += seconds
        distribution[row.project_id] = distribution.get(row.project_id, 0) + sum(values)
    for row in daily.values():
        row['focus_seconds'] = round(row['focus_seconds'], 3)
    session_scope = [*scoped(f.Session), f.Session.kind.in_(['focus', 'tracking']),
                     f.Session.status.in_(['completed', 'stopped']), f.Session.ended_at >= lo, f.Session.ended_at < hi]
    session_count, average_session = db.execute(select(func.count(), func.avg(f.Session.elapsed_seconds)).where(*session_scope)).one()
    session_history = [focus.view(x, instant) for x in db.scalars(select(f.Session).where(*session_scope).order_by(
        f.Session.ended_at.desc(), f.Session.id.desc()).offset(offset).limit(limit + 1))]
    active = db.scalar(select(f.Session).where(*scoped(f.Session), f.Session.status.in_(['running', 'paused'])))
    project_stats = [{'id': pid, 'name': name, 'tasks': total, 'completed': done or 0, 'progress': percentage(done or 0, total, None),
                      'focus_seconds': round(distribution.get(pid, 0), 3)} for pid, name, total, done in db.execute(
        select(Project.id, Project.name, func.count(Task.id), func.sum(Task.completed.cast(Integer))).outerjoin(Task, Task.project_id == Project.id).where(
            Project.id.in_(pids)).group_by(Project.id).order_by(Project.id).offset(offset).limit(limit + 1))]
    weeks, months = {}, {}
    streak = longest = 0
    for day, row in zip(days, daily.values()):
        active_study = row['lessons'] + row['quiz_attempts'] + row['reviews'] > 0
        streak = streak + 1 if active_study else 0
        longest = max(longest, streak)
        for dest, key in ((weeks, (day - timedelta(days=day.weekday())).isoformat()), (months, day.strftime('%Y-%m'))):
            target = dest.setdefault(key, {'date': key, **{k: 0 for k in row if k != 'date'}})
            for k, v in row.items():
                if k != 'date':
                    target[k] += v
    limitations = [
        'Progress, due cards, goals and milestones are current snapshots, not historical snapshots.',
        'Study time is unavailable: lesson reading is not timed. Completed planned minutes are self-reported and are shown for this page of plans only.',
        'Completion trends count currently completed tasks/lessons at their latest completion instant; reopening clears the instant. Older completions without timestamps are excluded.',
        'Study streaks count lesson completions, quiz attempts and reviews within the selected range only.',
        'Focus totals use time entries once, including manual/tracking work and ledger adjustments; breaks and running/paused sessions are excluded. Session statistics use original durations of ended sessions in range.',
        'Milestones lack completion timestamps. The completed milestone list is a current snapshot, not a recent-completion timeline.',
    ]
    if course_id is not None:
        limitations.append('The course filter limits Study metrics; Focus and tasks remain scoped to its project because no course-to-focus association exists.')
    if estimated:
        limitations.append('Legacy time entries without running segments use estimated proportional calendar allocation.')
    def page(rows):
        return {'items': rows[:limit], 'has_more': len(rows) > limit, 'offset': offset, 'limit': limit}
    unknown_lessons = db.scalar(select(func.count()).select_from(s.Lesson).where(*lesson_scope, s.Lesson.completed.is_(True), s.Lesson.completed_at.is_(None)))
    unknown_tasks = db.scalar(select(func.count()).select_from(Task).where(*scoped(Task), Task.completed.is_(True), Task.completed_at.is_(None)))
    result = {
        'range': {'start': days[0].isoformat(), 'end': days[-1].isoformat(), 'timezone': zone.key, 'preset': preset},
        'generated_at': focus.stamp(instant), 'ai_calls': 0, 'filters': {'workspace_id': workspace_id, 'project_id': project_id, 'course_id': course_id},
        'study': {'lessons': total_lessons, 'completed_lessons': done_lessons, 'completion_percentage': percentage(done_lessons, total_lessons, None),
                  'study_seconds': None, 'completed_planned_minutes_on_page': planned_minutes, 'quiz_attempts': attempt_count,
                  'average_quiz_score': round(average_score, 2) if average_score is not None else None,
                  'flashcards_reviewed': sum(ratings.values()), 'flashcards_due': due, 'review_ratings': {str(i): ratings.get(i, 0) for i in range(1, 5)},
                  'review_success_percentage': percentage(ratings.get(3, 0) + ratings.get(4, 0), sum(ratings.values()), None),
                  'streak_at_range_end': streak, 'longest_streak_in_range': longest, 'unknown_completion_dates': unknown_lessons,
                  'courses': page(courses), 'quiz_performance': page(quiz_per_course), 'plans': page(plans), 'upcoming_sessions_on_page': upcoming_study},
        'focus': {'total_seconds': round(sum(distribution.values()), 3), 'session_count': session_count,
                  'average_session_seconds': round(average_session, 3) if average_session is not None else None,
                  'active_session': focus.view(active, instant) if active else None, 'allocation_estimated': estimated,
                  'goals': page(goals), 'sessions': page(session_history)},
        'workspace': {'tasks': task_total, 'completed_tasks': task_done, 'progress': percentage(task_done, task_total, None),
                      'tasks_completed_in_range': sum(x['tasks'] for x in daily.values()), 'unknown_completion_dates': unknown_tasks,
                      'projects': page(project_stats), 'upcoming_tasks': page(upcoming_tasks),
                      'milestones_on_page': milestones},
        'daily': list(daily.values()), 'weekly': list(weeks.values()), 'monthly': list(months.values()), 'limitations': limitations,
    }
    # The result is fully materialized. Release the explicit read snapshot here,
    # before FastAPI schedules dependency cleanup in the shared thread pool.
    # Otherwise a concurrent Focus writer can wait on this reader while queued
    # requests occupy the threads needed to close it (SQLite DELETE journal).
    db.rollback()
    return result


def export_csv(data, kind):
    """Fixed schemas, RFC CSV quoting, formula neutralization for all string cells."""
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    def cell(value):
        if value is None:
            return ''
        value = str(value)
        return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')) else value
    def write(*values):
        writer.writerow([cell(x) for x in values])
    write('Kumuta AI', kind, data['range']['start'], data['range']['end'], data['range']['timezone'])
    write('metric', 'value', 'scope')
    sections = ['study', 'focus', 'workspace'] if kind == 'workspace' else [kind]
    for section in sections:
        for key, value in data[section].items():
            if value is None or isinstance(value, (int, float, bool)):
                write(f'{section}.{key}', value, 'See metric definitions in report limitations')
    write('date', 'lessons_completed', 'quiz_attempts', 'flashcard_reviews', 'tasks_completed', 'focused_seconds')
    for row in data['daily']:
        write(*(row[k] for k in ('date', 'lessons', 'quiz_attempts', 'reviews', 'tasks', 'focus_seconds')))
    for note in data['limitations']:
        write('definition', note)
    return output.getvalue()
