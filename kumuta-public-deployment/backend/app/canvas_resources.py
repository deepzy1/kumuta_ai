"""Board resource adapters over existing document, dataset and attachment storage."""
import base64
import hashlib
import json
from types import SimpleNamespace
from fastapi import HTTPException
from sqlalchemy import select, func
from .database import Attachment, Message, Conversation
from .document_models import DocumentChunk, StoredFile
from .board_models import BoardMediaLink, BoardResourceLink, BoardConversation
from . import boards, datasets, documents
from .canvas_resource_contract import ResourceRef

MAX_SOURCE_BYTES = 24000


def source(board, kind, sid, db, linked=True):
    if getattr(board,'_actor_id',board.owner_id) != board.owner_id:
        raise HTTPException(403,'Private source unavailable. Board access does not share original files or RAG evidence.')
    user=SimpleNamespace(id=board.owner_id)
    if kind=='document':
        row=boards.document_in_scope(board,sid,user,db)
        association=db.get(BoardResourceLink,(board.id,sid))
    elif kind=='dataset':
        if board.project_id:
            row=datasets.owned(board.project_id,sid,user,db)
        else:
            from .dataset_models import Dataset
            row=db.scalar(select(Dataset).where(Dataset.id==sid,Dataset.owner_id==board.owner_id,Dataset.board_id==board.id,Dataset.project_id.is_(None)))
            if row is None:raise HTTPException(404,'Dataset not found in this board')
        association=db.get(BoardMediaLink,(board.id,kind,sid))
    elif kind=='image':
        row=db.get(Attachment,sid); message=db.get(Message,row.message_id) if row else None
        if not message: raise HTTPException(404,'Image unavailable')
        conversation=boards.conversation_in_scope(board,message.conversation_id,user,db)
        if not db.get(BoardConversation,(board.id,conversation.id)) or row.attachment_mime not in ('image/png','image/jpeg','image/webp'):
            raise HTTPException(404,'Image is outside this board scope')
        association=db.get(BoardMediaLink,(board.id,kind,sid))
    else: raise HTTPException(422,'Unsupported resource type')
    if linked and association is None: raise HTTPException(404,'Resource is no longer linked to this board')
    return row


def image_bytes(row):
    try: return base64.b64decode(row.attachment_data,validate=True)
    except ValueError: raise HTTPException(409,'Stored image is invalid') from None


def fingerprint(kind,row):
    digest=hashlib.sha256(image_bytes(row)).hexdigest() if kind=='image' else row.sha256
    return hashlib.sha256(f'{kind}:{row.id}:{digest}:{getattr(row,"revision",1)}'.encode()).hexdigest()


def info(kind,row):
    result={'kind':kind,'source_id':row.id,'filename':row.attachment_name if kind=='image' else row.filename,
            'status':'ready' if kind=='image' else row.status,'fingerprint':fingerprint(kind,row),
            'revision':getattr(row,'revision',1),'error':getattr(row,'error',None),
            'format':row.attachment_mime.split('/')[-1] if kind=='image' else row.format if kind=='dataset' else row.filename.rsplit('.',1)[-1].lower()}
    if kind=='document':result.update(pages=row.pages,warning=row.warning)
    if kind=='dataset':result.update(sheets=json.loads(row.metadata_json))
    if kind=='image':
        from .attachments import fitz
        with fitz.open(stream=image_bytes(row),filetype=result['format']) as image:
            profiles=image[0].get_image_info()
        profile=profiles[0] if len(profiles)==1 else None
        if not profile or not profile.get('width') or not profile.get('height'):raise HTTPException(415,'Image dimensions are unavailable')
        if profile['width']*profile['height']>40000000:raise HTTPException(413,'Resource image exceeds 40 megapixels')
        result.update(width=profile['width'],height=profile['height'])
    return result


def listing(board,db):
    items=[info('document',r) for r in boards.resource_documents(board,SimpleNamespace(id=board.owner_id),db)]
    for link in db.scalars(select(BoardMediaLink).where(BoardMediaLink.board_id==board.id)):
        try:items.append(info(link.kind,source(board,link.kind,link.source_id,db)))
        except HTTPException as e:
            if e.status_code!=404:raise
    return items


def count_links(board,db):
    return sum(db.scalar(select(func.count()).select_from(model).where(model.board_id==board.id)) for model in (BoardResourceLink,BoardMediaLink))


def link(board,kind,sid,db):
    row=source(board,kind,sid,db,linked=False)
    if count_links(board,db)>=100 and not (db.get(BoardResourceLink,(board.id,sid)) if kind=='document' else db.get(BoardMediaLink,(board.id,kind,sid))):
        raise HTTPException(413,'Use at most 100 board resources')
    model=BoardResourceLink if kind=='document' else BoardMediaLink
    key=(board.id,sid) if kind=='document' else (board.id,kind,sid)
    if db.get(model,key) is None:
        db.add(BoardResourceLink(board_id=board.id,document_id=sid) if kind=='document' else BoardMediaLink(board_id=board.id,kind=kind,source_id=sid,**{('dataset_id' if kind=='dataset' else 'attachment_id'):sid}))
    return info(kind,row)


def checked_file(row,db):
    ledger=db.get(StoredFile,row.file_id)
    if not ledger:raise HTTPException(404,'Source file unavailable')
    path=documents.storage_path(ledger.storage_key)
    try:
        with path.open('rb') as f:raw=f.read(documents.MAX_FILE+1)
    except OSError:raise HTTPException(404,'Source file unavailable') from None
    if len(raw)>documents.MAX_FILE or hashlib.sha256(raw).hexdigest()!=row.sha256:raise HTTPException(409,'Resource source changed or is corrupt')


def preview(board,ref,db):
    row=source(board,ref.kind,ref.source_id,db)
    meta=info(ref.kind,row)
    if meta['fingerprint']!=ref.fingerprint:raise HTTPException(409,'Resource changed. Reopen its preview and select it again.')
    if meta['status']!='ready':raise HTTPException(409,meta['error'] or 'Resource is still processing')
    result={'resource':meta,'reference':ref.model_dump(),'ai_calls':0}
    if ref.kind=='document':
        checked_file(row,db)
        if ref.page is not None and (meta['format']!='pdf' or ref.page>row.pages):raise HTTPException(422,'Page reference is unavailable; only PDFs have page numbers')
        query=select(DocumentChunk).where(DocumentChunk.document_id==row.id)
        if ref.page is not None:query=query.where(DocumentChunk.page==ref.page)
        if ref.block_id is not None:query=query.where(DocumentChunk.id==ref.block_id)
        chunks=list(db.scalars(query.order_by(DocumentChunk.ordinal).limit(101)))
        if ref.block_id and not chunks:raise HTTPException(422,'Content block is unavailable')
        if not ref.page and not ref.block_id:chunks=chunks[:1] # Never retrieve whole documents implicitly.
        if len(chunks)>100:raise HTTPException(413,'Select a smaller page/block')
        items=[{'block_id':c.id,'page':c.page,'section':c.section,'text':c.content} for c in chunks]
        if ref.start is not None:
            if ref.end>len(items[0]['text']):raise HTTPException(422,'Passage offsets exceed the selected block')
            items[0]['text']=items[0]['text'][ref.start:ref.end]
        # Navigation metadata is bounded, text stays limited to this selection.
        nav=list(db.scalars(select(DocumentChunk).where(DocumentChunk.document_id==row.id).order_by(DocumentChunk.ordinal).limit(1000)))
        result.update(items=items,blocks=[{'block_id':c.id,'section':c.section,'page':c.page} for c in nav],warning=row.warning)
        if not items:result['warning']='No extracted text on this page. Scanned PDFs/OCR are unsupported.'
    elif ref.kind=='dataset':
        data=datasets.sheet_data(row,ref.sheet,db)
        cols=ref.columns or list(range(min(20,len(data['columns']))))
        if any(c>=len(data['columns']) for c in cols) or ref.row_start>=len(data['rows']) and data['rows'] or ref.row_end>len(data['rows']) and ref.row_start!=0:
            raise HTTPException(422,'Selected range is outside this worksheet')
        end=min(ref.row_end,len(data['rows']))
        result['reference'].update(sheet=data['name'],columns=cols,row_end=max(end,1))
        result.update(columns=[data['columns'][i] for i in cols],items=[[r[i] for i in cols] for r in data['rows'][ref.row_start:end]],
                      row_count=len(data['rows']),all_columns=data['columns'],sheets=[s['name'] for s in json.loads(row.metadata_json)],warning=data.get('warnings',[]))
    # Fail visibly; context is never silently truncated.
    if len(json.dumps(result.get('items',[]),ensure_ascii=False).encode())>MAX_SOURCE_BYTES:raise HTTPException(413,'Selected resource content exceeds 24000 bytes. Select a smaller passage or range.')
    return result


def column_name(index):
    value='';index+=1
    while index:index,r=divmod(index-1,26);value=chr(65+r)+value
    return value


def resolve(board,ref,db):
    p=preview(board,ref,db);r=p['reference'];m=p['resource'];label=m['filename']
    if ref.kind=='document':
        part=f'p. {ref.page}' if ref.page else f'block {p["items"][0]["block_id"]}' if p['items'] else 'no extracted text'
        if ref.start is not None:part+=f' · characters {ref.start}–{ref.end}'
        evidence=p['items']
    elif ref.kind=='dataset':
        cols=r['columns']; start=r['row_start'];end=min(r['row_end'],p['row_count'])
        ranges=', '.join(f'{column_name(c)}{start+2}:{column_name(c)}{end+1}' for c in cols)
        part=f'{r["sheet"]} · {ranges}'
        if m['format']=='csv':part+=f' · data rows {start+1}–{end}'
        if not p['items']:raise HTTPException(422,'Selected worksheet range contains no data rows')
        evidence={'columns':[{k:c[k] for k in ('name','type')} for c in p['columns']],'rows':p['items']}
    else:part=f'image · {m["width"]} × {m["height"]}';evidence={'width':m['width'],'height':m['height'],'visual_consent_required':True}
    return {'source_type':'resource','reference':r,'filename':label,'label':f'{label} · {part}','content':evidence}


def visual_parts(board,refs,db):
    from .gemini import types
    parts=[];total=0;pixels=0
    for ref in refs:
        if ref.kind!='image':continue
        row=source(board,'image',ref.source_id,db);meta=info('image',row);raw=image_bytes(row);total+=len(raw);pixels+=meta['width']*meta['height']
        if total>2*1024*1024 or pixels>2000000:raise HTTPException(413,'Visual resources exceed 2 MiB or 2 million pixels. Upload a smaller image.')
        parts.append(types.Part.from_bytes(data=raw,mime_type=row.attachment_mime))
    return parts
