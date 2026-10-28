"""Authenticated job/event/artifact contracts on the existing FastAPI app."""
import asyncio
import json
import time
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker
from pydantic import ValidationError
from fastapi.exceptions import RequestValidationError
from starlette.datastructures import UploadFile
from .attachments import read_attachments, MAX_TOTAL_FILES
from . import boards, canvas_generation as service, workspaces
from .board_api import BoundedBoardRoute
from .canvas_generation_models import GenerationJob as Job, GenerationEvent as Event, CanvasArtifact as Artifact, ArtifactVersion as Version, ArtifactRenderReport
from .canvas_generation_schemas import GenerationRequest, PlacementRequest, DuplicateRequest, RenderReport, CanvasPreferences
from .database import User, now
from . import canvas_selection as selection


class GenerationRoute(BoundedBoardRoute):
    max_request_bytes = MAX_TOTAL_FILES + 65536
    max_request_error = 'Canvas uploads exceed the 20 MB total limit plus request envelope.'


def register(app, user_dependency, db_dependency):
    router = APIRouter(prefix='/boards/{bid}', route_class=GenerationRoute)

    @app.patch('/settings/canvas')
    def preferences(data:CanvasPreferences,user=Depends(user_dependency),db=Depends(db_dependency)):
        user.canvas_generation_mode = data.mode
        db.commit()
        return {'mode':user.canvas_generation_mode}

    @router.post('/selection/resolve')
    def resolve_selection(bid:int,data:selection.SelectionRequest,user=Depends(user_dependency),db=Depends(db_dependency)):
        board=boards.owned(bid,user,db,writable=True)
        return selection.resolve(board,data,db)

    @router.post('/generations',status_code=201)
    async def create(bid:int,request:Request,user=Depends(user_dependency),db=Depends(db_dependency)):
        # Same contract for JSON and shared multipart uploads; authorize before decoding images.
        boards.owned(bid,user,db,writable=True)
        fields=[]
        try:
            if request.headers.get('content-type','').startswith('multipart/form-data'):
                async with request.form(max_files=5,max_fields=2,max_part_size=16384) as form:
                    data=GenerationRequest.model_validate_json(form.get('request',''))
                    uploads=form.getlist('attachments')
                    if any(not isinstance(f,UploadFile) for f in uploads):
                        raise HTTPException(422,'Invalid image upload.')
                    fields=await read_attachments(uploads,images_only=True)
            else:
                data=GenerationRequest.model_validate(await request.json())
        except ValidationError as exc:
            raise RequestValidationError(exc.errors()) from None
        except (ValueError,TypeError):
            raise HTTPException(422,'Invalid generation request.') from None
        row=service.create_job(bid,data,user,db,attachments=fields)
        return service.job_view(row,db)

    @router.get('/generations')
    def listing(bid:int,limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0,le=1000),conversation_id:int|None=None,unassigned:bool=False,user=Depends(user_dependency),db=Depends(db_dependency)):
        board = boards.owned(bid,user,db)
        if boards.role(board,user,db)=='viewer': raise HTTPException(403,'Generation history requires editing permission.')
        query = select(Job).where(Job.board_id==bid,Job.owner_id==user.id)
        if conversation_id is not None:
            boards.conversation_in_scope(board,conversation_id,user,db)
            from .board_models import BoardConversation
            if db.get(BoardConversation,(bid,conversation_id)) is None:
                raise HTTPException(404,'Conversation is not linked to this board')
            query = query.where(Job.conversation_id==conversation_id)
        elif unassigned:
            query = query.where(Job.conversation_id.is_(None))
        rows=list(db.scalars(query.order_by(Job.created_at.desc(),Job.id.desc()).offset(offset).limit(limit+1)))
        return {'items':[service.job_view(r,db) for r in rows[:limit]],'has_more':len(rows)>limit,'openui_enabled':service.OPENUI_ENABLED,'limits':{'daily_requests':service.DAILY_JOBS,'active_per_user':1,'global_active':service.MAX_ACTIVE}}

    @router.get('/generations/{jid}')
    def detail(bid:int,jid:str,user=Depends(user_dependency),db=Depends(db_dependency)):
        return service.job_view(service.owned_job(bid,jid,user,db),db)

    @router.post('/generations/{jid}/cancel')
    def cancel(bid:int,jid:str,user=Depends(user_dependency),db=Depends(db_dependency)):
        workspaces.lock_writes(user,db)
        row=service.owned_job(bid,jid,user,db)
        if row.status not in service.TERMINAL:
            service.transition(db,row,'cancelled','Generation cancelled. Submitted provider work may still be billed.');db.commit()
        return service.job_view(row,db)

    @router.get('/generations/{jid}/events')
    def events(bid:int,jid:str,request:Request,after:int=Query(0,ge=0,le=100000),user=Depends(user_dependency),db=Depends(db_dependency)):
        service.owned_job(bid,jid,user,db)
        sessions=sessionmaker(bind=db.get_bind(),expire_on_commit=False)
        uid=user.id
        # Authentication uses bearer headers, never credentials in EventSource URLs.
        async def stream():
            cursor=after; started=time.monotonic()
            while time.monotonic()-started<10:
                if await request.is_disconnected(): return
                frames=[];revoked=False;terminal=False
                with sessions() as fresh:
                    owner=fresh.get(User,uid)
                    try:
                        from .browser_sessions import stream_valid
                        from .main import SECRET
                        if not stream_valid(request,uid,fresh,SECRET): raise HTTPException(401,'Session expired')
                        if owner is None: raise HTTPException(404,'Account no longer exists')
                        job=service.owned_job(bid,jid,owner,fresh)
                    except HTTPException:
                        revoked=True
                    if not revoked:
                        rows=list(fresh.scalars(select(Event).where(Event.job_id==jid,Event.sequence>cursor).order_by(Event.sequence)))
                        snapshot=service.job_view(job,fresh)
                        for row in rows:
                            cursor=row.sequence
                            event={'job_id':jid,'sequence':row.sequence,'status':row.status,'created_at':row.created_at}
                            frames.append(f'id: {row.sequence}\nevent: {row.status}\ndata: {service.encoded(event)}\n\n')
                        frames.append(f'event: snapshot\ndata: {service.encoded(snapshot)}\n\n')
                        terminal=job.status in service.TERMINAL
                # Release the read transaction before network backpressure/waits.
                if revoked:
                    yield 'event: done\ndata: {"access_revoked":true}\n\n';return
                for frame in frames:
                    # A slow consumer may resume after revocation/logout. Recheck
                    # before each frame rather than releasing a stale snapshot.
                    with sessions() as fresh:
                        try:
                            if not stream_valid(request,uid,fresh,SECRET): raise HTTPException(401)
                            service.owned_job(bid,jid,fresh.get(User,uid),fresh)
                        except HTTPException:
                            revoked=True
                    if revoked:
                        yield 'event: done\ndata: {"access_revoked":true}\n\n';return
                    yield frame
                if terminal:
                    yield 'event: done\ndata: {}\n\n';return
                await asyncio.sleep(.5)
            yield 'event: done\ndata: {"reconnect":true}\n\n'
        return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'private, no-store','X-Accel-Buffering':'no'})

    @router.get('/artifacts')
    def artifacts(bid:int,limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0,le=1000),user=Depends(user_dependency),db=Depends(db_dependency)):
        board=boards.owned(bid,user,db)
        if boards.role(board,user,db)=='viewer': raise HTTPException(403,'Artifact proposals require editing permission.')
        rows=list(db.scalars(select(Artifact).where(Artifact.board_id==bid,Artifact.owner_id==user.id).order_by(Artifact.created_at.desc()).offset(offset).limit(limit+1)))
        return {'items':[service.artifact_view(r,db) for r in rows[:limit]],'has_more':len(rows)>limit,'ai_calls':0}

    @router.get('/artifacts/{aid}')
    def artifact(bid:int,aid:str,user=Depends(user_dependency),db=Depends(db_dependency)):
        return service.artifact_view(service.owned_artifact(bid,aid,user,db),db)

    @router.post('/artifacts/{aid}/placement')
    def place(bid:int,aid:str,data:PlacementRequest,user=Depends(user_dependency),db=Depends(db_dependency)):
        try: return service.place(bid,aid,data,user,db)
        except (ValidationError,ValueError):
            raise HTTPException(422,'Generated placement is invalid. Your saved scene is preserved.') from None

    @router.post('/artifacts/{aid}/versions/{version}/render')
    def rendered(bid:int,aid:str,version:int,data:RenderReport,user=Depends(user_dependency),db=Depends(db_dependency)):
        workspaces.lock_writes(user,db)
        boards.owned(bid,user,db,writable=True)
        service.owned_artifact(bid,aid,user,db)
        if db.get(Version,(aid,version)) is None: raise HTTPException(404,'Artifact version not found')
        row=db.get(ArtifactRenderReport,(aid,version))
        if row is None:
            row=ArtifactRenderReport(artifact_id=aid,version=version,status=data.status);db.add(row)
        row.status=data.status;row.updated_at=now();db.commit()
        return {'rendering_status':row.status,'reported_by':'authenticated_client','ai_calls':0}

    @router.post('/artifacts/{aid}/duplicate',status_code=201)
    def duplicate(bid:int,aid:str,data:DuplicateRequest,user=Depends(user_dependency),db=Depends(db_dependency)):
        workspaces.lock_writes(user,db)
        service.owned_artifact(bid,aid,user,db,writable=True)
        source=db.get(Version,(aid,data.version))
        if source is None: raise HTTPException(404,'Artifact version not found')
        provenance=f'{aid}:{data.version}'
        existing=db.scalar(select(Artifact).where(Artifact.owner_id==user.id,Artifact.request_key=='copy_'+data.request_key))
        if existing:
            if existing.board_id!=bid or existing.copied_from!=provenance:
                raise HTTPException(409,'Duplicate request key was already used for another artifact version.')
            return service.artifact_view(existing,db)
        if db.scalar(select(func.count()).select_from(Artifact).where(Artifact.owner_id==user.id))>=1000:
            raise HTTPException(413,'Generated artifact account limit reached (1000).')
        service.artifact_budget(user,db,len(source.content_json.encode()))
        row=Artifact(id=uuid4().hex,owner_id=user.id,board_id=bid,request_key='copy_'+data.request_key,copied_from=provenance)
        db.add(row);db.flush()
        db.add(Version(artifact_id=row.id,version=1,engine=source.engine,content_json=source.content_json))
        db.commit()
        return service.artifact_view(row,db)

    app.include_router(router)
