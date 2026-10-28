"""Local search/calculation and reviewed reports on existing Canvas stores."""
import hashlib
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import func, select
from . import boards, workspaces, canvas_selection as selection, canvas_intelligence as service
from . import canvas_generation as generation
from .board_api import BoundedBoardRoute
from .canvas_artifacts import Strict
from .canvas_selection import SelectionRequest
from .canvas_resource_contract import ResourceRef
from .canvas_generation_models import GenerationJob as Job, GenerationEvent as Event, CanvasArtifact as Artifact, ArtifactVersion as Version
from .quickui import Specification
from .report_models import DataReport
from .data_reports import Widget, validate_widgets


class LocalProposal(Strict):
    request_key: str = Field(pattern=r'^[a-zA-Z0-9_-]{8,80}$')
    selection: SelectionRequest | None = None
    source_job_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    title: str = Field(default='Research report', min_length=1, max_length=200)
    save_data_report: bool = False


def register(app, user_dependency, db_dependency):
    router=APIRouter(prefix='/boards/{bid}/intelligence',route_class=BoundedBoardRoute)

    @router.post('/search')
    def search(bid:int, data:SelectionRequest, user=Depends(user_dependency), db=Depends(db_dependency)):
        board=boards.owned(bid,user,db,owner_only=True)
        if not data.intelligence or data.intelligence.operation!='search': raise HTTPException(422,'Choose the explicit search action and source scope.')
        context=selection.resolve(board,data,db)
        return {'context':context,'ai_calls':0,'message':'Matching authorized passages.' if context.get('resources') else 'Insufficient evidence: no matching passages in this source scope.'}

    @router.post('/analyze')
    def analyze(bid:int, data:SelectionRequest, user=Depends(user_dependency), db=Depends(db_dependency)):
        board=boards.owned(bid,user,db,owner_only=True)
        if not data.intelligence or data.intelligence.scope=='selection' or not data.intelligence.analyses:
            raise HTTPException(422,'Choose a whole-resource scope and restricted specifications for local calculation.')
        context=selection.resolve(board,data,db)
        computed=service.calculate(board,data.intelligence.analyses,[ResourceRef(**r) for r in context['retrieval']['source_refs']],db)
        return {'context':context,'computed':computed,'visual':service.visual_content(computed),'ai_calls':0}

    @router.post('/proposals',status_code=201)
    def proposal(bid:int, data:LocalProposal, user=Depends(user_dependency), db=Depends(db_dependency)):
        workspaces.lock_writes(user,db)
        board=boards.owned(bid,user,db,writable=True,owner_only=True)
        digest=hashlib.sha256(service.encoded(data.model_dump()).encode()).hexdigest()
        old=db.scalar(select(Job).where(Job.owner_id==user.id,Job.request_key==data.request_key))
        if old:
            if old.request_hash!=digest or old.board_id!=bid: raise HTTPException(409,'Request key already used for different content.')
            return generation.artifact_view(generation.owned_artifact(bid,old.artifact_id,user,db),db)
        if bool(data.selection)==bool(data.source_job_id): raise HTTPException(422,'Choose local analysis or one completed source answer.')
        text=''
        if data.source_job_id:
            original=generation.owned_job(bid,data.source_job_id,user,db)
            if original.status!='completed' or original.engine!='T': raise HTTPException(422,'Review a completed grounded answer before saving a report.')
            context=selection.saved_selection(db,original.id)
            if not context or not context.get('retrieval'): raise HTTPException(422,'This answer has no D7-7 source provenance.')
            selection.verify(board,context,db)
            computed=context.get('verified_analysis')
            text=original.reply_text or ''
        else:
            if not data.selection.intelligence or data.selection.intelligence.scope=='selection': raise HTTPException(422,'Choose a complete-resource analysis scope.')
            context=selection.resolve(board,data.selection,db)
            computed=service.calculate(board,data.selection.intelligence.analyses,[ResourceRef(**r) for r in context['retrieval']['source_refs']],db)
            context['verified_analysis']=computed
        if computed:
            content=service.visual_content(computed,data.title)
        else:
            # Reviewed prose is retained verbatim in the existing job, projected
            # into text-only cards. No second report renderer or export engine.
            if len(text)>4200: raise HTTPException(413,'Reviewed report exceeds 4200 characters. Request a shorter report before saving.')
            pieces=[text[i:i+300] for i in range(0,len(text),300)] or ['Insufficient evidence.']
            payload=Specification.model_validate({'title':data.title,'blocks':[
                {'type':'cards','title':'Reviewed findings','items':[{'label':f'Passage {i+1}','detail':p} for i,p in enumerate(pieces)]},
                {'type':'cards','title':'Scope and limitations','items':[
                    {'label':'Scope','detail':context['retrieval']['coverage']},
                    {'label':'Sources','detail':'; '.join(dict.fromkeys(r['filename'] for r in context.get('resources',[])))[:300]},
                    {'label':'Limitations','detail':'AI-authored findings require review. Extracted evidence only; no OCR, semantic search or implicit joins.'}]}]})
            content={'engine':'B','format':'openui-lang-v1','capabilities':['local-state'],'payload':payload.model_dump()}
        if db.scalar(select(func.count()).select_from(Job).where(Job.owner_id==user.id))>=1000 or db.scalar(select(func.count()).select_from(Artifact).where(Artifact.owner_id==user.id))>=1000:
            raise HTTPException(413,'Canvas history limit reached (1000 jobs/artifacts).')
        generation.artifact_budget(user,db,len(service.encoded(content).encode()))
        aid,jid=uuid4().hex,uuid4().hex
        artifact=Artifact(id=aid,owner_id=user.id,board_id=bid,request_key='local_'+data.request_key)
        db.add(artifact);db.flush()
        job=Job(id=jid,owner_id=user.id,board_id=bid,artifact_id=aid,request_key=data.request_key,request_hash=digest,
                prompt=data.title,engine='B',output_format='openui-lang-v1',status='completed',version=1,reply_text=text or 'Verified local analysis proposal. Review before Accept.')
        db.add(job);db.flush()
        envelope={'selection_v1':context,'reviewed_from_job':data.source_job_id,'provider_calls':0}
        if data.save_data_report:
            if not computed or not board.project_id: raise HTTPException(422,'Project dataset reports require verified calculations.')
            workspaces.owned_project(board.project_id,user,db,writable=True)
            if db.scalar(select(func.count()).select_from(DataReport).where(DataReport.owner_id==user.id,DataReport.project_id==board.project_id))>=100:
                raise HTTPException(413,'Use at most 100 reports per project.')
            widgets=[Widget(key=f'result_{i}',title=o['dataset']['name'][:120],dataset_id=o['dataset']['id'],
                            source_sha256=o['dataset']['sha256'],spec=o['spec']) for i,o in enumerate(computed['results'])]
            saved=DataReport(owner_id=user.id,project_id=board.project_id,name=data.title,
                             description=f'Canvas board {bid}; artifact {aid}; explicit source scope; complete worksheet calculations.',
                             configuration=service.encoded(validate_widgets(board.project_id,widgets,user,db)))
            db.add(saved);db.flush();envelope['data_report_id']=saved.id
        db.add(Event(job_id=jid,sequence=1,status='completed',preview_json=service.encoded(envelope)))
        db.add(Version(artifact_id=aid,version=1,engine='B',source_job_id=jid,content_json=service.encoded(content)))
        db.commit()
        return generation.artifact_view(artifact,db)

    app.include_router(router)
