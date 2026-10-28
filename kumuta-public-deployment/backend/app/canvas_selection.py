"""Structured-first, board-authorized selection resolution. No provider calls."""
import hashlib
import json
import math
from typing import Literal
from fastapi import HTTPException
from pydantic import Field, model_validator
from .canvas_artifacts import Strict, ArtifactID
from .board_models import BoardSceneRevision
from .canvas_resource_contract import ResourceRef
from .canvas_intelligence_contract import IntelligenceRequest
from . import canvas_resources as resource_service

MAX_CONTEXT_BYTES = 32000
MAX_ELEMENTS = 120


class Bounds(Strict):
    x: float = Field(ge=-1e6, le=1e6, allow_inf_nan=False)
    y: float = Field(ge=-1e6, le=1e6, allow_inf_nan=False)
    width: float = Field(gt=0, le=12000, allow_inf_nan=False)
    height: float = Field(gt=0, le=12000, allow_inf_nan=False)


class SelectionRequest(Strict):
    expected_revision: int = Field(ge=0)
    element_ids: list[ArtifactID] = Field(default_factory=list, max_length=MAX_ELEMENTS)
    region: Bounds | None = None
    action: Literal['ask', 'explain', 'summarize', 'suggest', 'modify', 'derive'] = 'ask'
    table_scopes: list['TableScope'] = Field(default_factory=list, max_length=16)
    visual: bool = False
    resources: list[ResourceRef] = Field(default_factory=list, max_length=8)
    intelligence: IntelligenceRequest | None = None

    @model_validator(mode='after')
    def valid(self):
        if (not self.element_ids and not self.region and not self.resources and not self.intelligence) or (self.element_ids and self.region):
            raise ValueError('Choose element IDs or a region.')
        if len(set(self.element_ids)) != len(self.element_ids):
            raise ValueError('Duplicate selection IDs.')
        if len({(s.anchor_id,s.block_index) for s in self.table_scopes}) != len(self.table_scopes):
            raise ValueError('Duplicate table scope.')
        return self


class TableScope(Strict):
    anchor_id: ArtifactID
    block_index: int = Field(ge=0, le=15)
    scope: Literal['selected','filtered','visible']


SelectionRequest.model_rebuild()


def dumps(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def bounds(element):
    # Conservative rotated rectangle bounds also enclose freehand/connector points.
    x, y, w, h = (element.get(k, 0) for k in ('x', 'y', 'width', 'height'))
    a = element.get('angle', 0)
    rw, rh = abs(w * math.cos(a)) + abs(h * math.sin(a)), abs(w * math.sin(a)) + abs(h * math.cos(a))
    return dict(x=x+w/2-rw/2, y=y+h/2-rh/2, width=rw, height=rh)


def intersects(a, b):
    return a['x'] <= b['x']+b['width'] and b['x'] <= a['x']+a['width'] and a['y'] <= b['y']+b['height'] and b['y'] <= a['y']+a['height']


def current_scene(board, db):
    row = db.get(BoardSceneRevision, (board.id, board.current_revision))
    return json.loads(row.scene_json) if row else {'elements': [], 'artifacts': []}


def provenance(db, board, selected):
    from .canvas_generation_models import CanvasArtifact, ArtifactVersion
    refs = []
    for element in selected:
        ident = element['id']
        if '_v' not in ident: continue
        aid, _, suffix = ident.partition('_v')
        number = suffix.split('-', 1)[0]
        if len(aid) != 32 or not number.isdigit(): continue
        artifact = db.get(CanvasArtifact, aid)
        if artifact and artifact.board_id == board.id and artifact.owner_id == board.owner_id and db.get(ArtifactVersion, (aid, int(number))):
            ref = {'artifact_id': aid, 'version': int(number)}
            if ref not in refs: refs.append(ref)
    return refs


def resolve(board, request, db, scene=None):
    if board.current_revision != request.expected_revision:
        raise HTTPException(409, 'Selection is stale. Select the saved content again.')
    scene = scene if scene is not None else current_scene(board, db)
    live = {e['id']: e for e in scene['elements'] if not e.get('isDeleted')}
    if request.region:
        region = request.region.model_dump()
        ids = {i for i, e in live.items() if intersects(bounds(e), region)}
    else:
        ids = set(request.element_ids)
        if not ids <= live.keys():
            raise HTTPException(422, 'Selection references missing or unauthorized elements.')
    # Bound labels are part of the selected shape; unrelated neighbours stay private.
    ids.update(i for i, e in live.items() if e.get('containerId') in ids)
    if not ids and not request.resources and not request.intelligence:
        raise HTTPException(422, 'Select content on the canvas first.')
    if len(ids) > MAX_ELEMENTS:
        raise HTTPException(413, 'Select at most 120 elements including labels.')
    selected = [e for e in scene['elements'] if e['id'] in ids]
    widgets = [a for a in scene.get('artifacts', []) if a['anchor_id'] in ids]
    wb = {a['anchor_id']: a for a in widgets}
    frames = [f for f in scene.get('resources',[]) if f['anchor_id'] in ids]
    refs = list(request.resources)
    for f in frames:
        ref=ResourceRef(**f['reference'])
        if not any(r.kind==ref.kind and r.source_id==ref.source_id for r in refs):refs.append(ref)
    if len(refs)>8:raise HTTPException(413,'Select at most eight resources')
    retrieval=None
    if request.intelligence:
        if getattr(board,'_actor_id',board.owner_id) != board.owner_id:
            raise HTTPException(403,'Fresh RAG evidence requires private source access.')
        from .canvas_intelligence import retrieve
        if request.intelligence.scope!='selection' and (ids or request.region):
            raise HTTPException(422,'Resource scopes cannot silently include native selections. Choose Selection for mixed evidence.')
        resources,retrieval=retrieve(board,request.intelligence,refs,db)
    else:
        resources=[dict(resource_service.resolve(board,r,db),citation=f'R{i+1}') for i,r in enumerate(refs)]
    boxes = [bounds(e) for e in selected] or [dict(x=0,y=0,width=1,height=1)]
    x, y = min(b['x'] for b in boxes), min(b['y'] for b in boxes)
    union = dict(x=x, y=y, width=max(1,max(b['x']+b['width'] for b in boxes)-x), height=max(1,max(b['y']+b['height'] for b in boxes)-y))
    if max(union['width'], union['height']) > 12000:
        raise HTTPException(413, 'Selection spans more than 12000 scene units.')
    native = []
    for e in selected:
        if e['id'] in wb or any(f['anchor_id']==e['id'] for f in frames): continue
        item = {k: e[k] for k in ('id', 'type', 'x', 'y', 'width', 'height', 'angle', 'text', 'originalText', 'strokeColor', 'backgroundColor', 'fillStyle', 'strokeWidth', 'strokeStyle', 'fontSize', 'textAlign', 'points') if k in e}
        item['source_type'] = 'native'
        for k in ('startBinding', 'endBinding'):
            binding = e.get(k)
            if binding and binding.get('elementId') in ids: item[k] = binding
        if e.get('containerId') in ids: item['containerId'] = e['containerId']
        native.append(item)
    structured = json.loads(dumps([{'source_type': 'widget', **{k:a[k] for k in ('id','anchor_id','engine','payload','state','format') if k in a}, 'geometry':bounds(live[a['anchor_id']])} for a in widgets]))
    from .intelligent_ui import project_table, calculator_results
    scopes={(s.anchor_id,s.block_index):s.scope for s in request.table_scopes}
    used=set()
    for widget in structured:
        if widget['engine']!='B': continue
        widget['table_context']=[]
        widget['calculator_results']=[]
        for index, block in enumerate(widget['payload']['blocks']):
            if block['type']=='calculator' and block['operation']=='formula':
                widget['calculator_results'].append({'block_index':index,'results':calculator_results(block,widget.get('state',{}).get(str(index)))})
            if block['type']!='table': continue
            key=(widget['anchor_id'],index)
            value=widget.get('state',{}).get(str(index),{})
            scope=scopes.get(key,'selected' if isinstance(value,dict) and value.get('selected') else 'filtered')
            if key in scopes: used.add(key)
            projection=project_table(block,value,scope)
            widget['table_context'].append({'block_index':index,**projection})
            block['rows']=projection['rows']
            widget.get('state',{}).pop(str(index),None)
    if used!=set(scopes): raise HTTPException(422,'Table scope references a table outside the selection.')
    visual_required = any(r.kind=='image' for r in refs) or any(e['type'] in ('image','freedraw') for e in selected) or any(a['engine']=='C' for a in widgets)
    # Scriptless C source is not an enabled generative renderer; no HTML/code forwarded.
    for a in structured:
        if a['engine']=='C': a.pop('payload', None)
    # Hash the authoritative selected objects, not caller-supplied definitions.
    selected_files={e['fileId']:hashlib.sha256(dumps(scene.get('files',{}).get(e['fileId'])).encode()).hexdigest() for e in selected if e.get('fileId')}
    fingerprint = hashlib.sha256(dumps([selected, widgets, selected_files]+([resources] if resources else [])).encode()).hexdigest()
    result = {'schema_version':2 if resources else 1, 'kind':'region' if request.region else 'elements', 'board_id':board.id, 'scene_revision':board.current_revision,
              'element_ids':sorted(ids), 'bounds':request.region.model_dump() if request.region else union,
              'native':native, 'widgets':structured, 'artifact_refs':provenance(db, board, selected),
              'fingerprint':fingerprint, 'action':request.action, 'visual_requested':request.visual,
              'visual_required':visual_required, 'visual_attached':False}
    if request.table_scopes: result['table_scopes']=[s.model_dump() for s in request.table_scopes]
    if resources:result['resources']=resources
    if retrieval:
        result['schema_version']=3
        result['retrieval']=retrieval
        result['intelligence_request']=request.intelligence.model_dump()
        result['native_fingerprint']=hashlib.sha256(dumps([selected,widgets,selected_files]).encode()).hexdigest()
    if len(dumps(result).encode()) > MAX_CONTEXT_BYTES:
        raise HTTPException(413, 'Selected context exceeds 32000 bytes. Select less content.')
    return result


def verify(board, snapshot, db):
    if snapshot.get('retrieval'):
        from .canvas_intelligence import verify_sources
        verify_sources(board,snapshot,db)
        # Source hashes and immutable chunks are authoritative; new board links
        # must not expand the frozen scope or change the original ranking.
        scene=current_scene(board,db)
        chosen=[e for e in scene['elements'] if e['id'] in snapshot['element_ids'] and not e.get('isDeleted')]
        widgets=[a for a in scene.get('artifacts',[]) if a['anchor_id'] in snapshot['element_ids']]
        files={e['fileId']:hashlib.sha256(dumps(scene.get('files',{}).get(e['fileId'])).encode()).hexdigest() for e in chosen if e.get('fileId')}
        if hashlib.sha256(dumps([chosen,widgets,files]).encode()).hexdigest()!=snapshot['native_fingerprint']:
            raise HTTPException(409,'Selected content changed. Select it again.')
        return snapshot
    request = SelectionRequest(expected_revision=board.current_revision, element_ids=snapshot['element_ids'], action=snapshot['action'], visual=snapshot['visual_requested'], resources=[r['reference'] for r in snapshot.get('resources',[])],table_scopes=snapshot.get('table_scopes',[]))
    current = resolve(board, request, db)
    if current['fingerprint'] != snapshot['fingerprint']:
        raise HTTPException(409, 'Selected content changed. Select it again before generating or accepting.')
    return current


def saved_selection(db, job_id):
    from .canvas_generation_models import GenerationEvent
    event = db.get(GenerationEvent, (job_id, 1)) if job_id else None
    envelope = json.loads(event.preview_json) if event and event.preview_json else {}
    return envelope.get('selection_v1')


def public_context(board, snapshot, db):
    """Keep historical labels, reauthorize content each time job/version views open."""
    if not snapshot or not (snapshot.get('resources') or snapshot.get('retrieval')):return snapshot
    result=json.loads(dumps(snapshot))
    for item in result.get('resources',[]):
        ref=ResourceRef(**item['reference'])
        try:
            row=resource_service.source(board,ref.kind,ref.source_id,db) if board else None
            if row is None or resource_service.fingerprint(ref.kind,row)!=ref.fingerprint or getattr(row,'status','ready')!='ready':
                raise HTTPException(404,'Resource unavailable')
            if ref.kind!='image':
                key=(board.id,ref.kind,ref.source_id,ref.fingerprint)
                checked=db.info.setdefault('canvas_public_sources',set())
                if key not in checked:resource_service.checked_file(row,db);checked.add(key)
        except HTTPException:
            item.pop('content',None);item['unavailable']=True
    if result.get('retrieval'):
        try:
            from .canvas_intelligence import verify_sources
            verify_sources(board,result,db)
        except (HTTPException,AttributeError):
            result.pop('verified_analysis',None)
            result['retrieval']['unavailable']=True
            for item in result.get('resources',[]):
                item.pop('content',None);item['unavailable']=True
    return result
