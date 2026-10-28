"""Board-scoped preview/library facade; original processing endpoints own uploads."""
from pathlib import Path
from typing import Literal
from fastapi import Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from . import boards, workspaces, canvas_resources as service
from .board_models import BoardResourceLink, BoardMediaLink, BoardConversation
from .document_models import Document
from .dataset_models import Dataset
from .database import Conversation, Message, Attachment
from .canvas_resource_contract import ResourceRef
from .canvas_artifacts import Strict
from pydantic import Field


class Link(Strict):
    kind: Literal['document','dataset','image']
    source_id: int = Field(gt=0)


def register(app,user_dependency,db_dependency):
    base='/boards/{bid}/resource-library'
    def endpoint(path,method):
        return next(r.endpoint for r in app.routes if getattr(r,'path',None)==path and method in getattr(r,'methods',[]))

    @app.get(base)
    def listing(bid:int,user=Depends(user_dependency),db=Depends(db_dependency)):
        return {'items':service.listing(boards.owned(bid,user,db,owner_only=True),db),'ai_calls':0}

    @app.get(base+'/available')
    def available(bid:int,user=Depends(user_dependency),db=Depends(db_dependency)):
        board=boards.owned(bid,user,db,owner_only=True);items=[]
        cids=list(db.scalars(select(BoardConversation.conversation_id).where(BoardConversation.board_id==bid)))
        docs=db.scalars(select(Document).where(Document.user_id==user.id, (Document.project_id==board.project_id) if board.project_id else Document.conversation_id.in_(cids)).order_by(Document.id.desc()).limit(100))
        for row in docs:
            try:items.append(service.info('document',service.source(board,'document',row.id,db,False)))
            except HTTPException as e:
                if e.status_code!=404:raise
        items.extend(service.info('dataset',r) for r in db.scalars(select(Dataset).where(Dataset.owner_id==user.id,Dataset.project_id==board.project_id,True if board.project_id else Dataset.board_id==bid).order_by(Dataset.id.desc()).limit(100)))
        images=db.scalars(select(Attachment).join(Message).join(Conversation,Conversation.id==Message.conversation_id).where(Conversation.user_id==user.id,Message.conversation_id.in_(cids),Attachment.attachment_mime.in_(['image/png','image/jpeg','image/webp'])).order_by(Attachment.id.desc()).limit(100))
        items.extend(service.info('image',r) for r in images)
        return {'items':items,'ai_calls':0,'limit_per_type':100}

    @app.post(base,status_code=201)
    def link(bid:int,data:Link,user=Depends(user_dependency),db=Depends(db_dependency)):
        workspaces.lock_writes(user,db);board=boards.owned(bid,user,db,writable=True,owner_only=True)
        result=service.link(board,data.kind,data.source_id,db);db.commit();return result

    @app.delete(base+'/{kind}/{sid}')
    def unlink(bid:int,kind:Literal['document','dataset','image'],sid:int,user=Depends(user_dependency),db=Depends(db_dependency)):
        workspaces.lock_writes(user,db);boards.owned(bid,user,db,writable=True,owner_only=True)
        row=db.get(BoardResourceLink,(bid,sid)) if kind=='document' else db.get(BoardMediaLink,(bid,kind,sid))
        if not row:raise HTTPException(404,'Resource association unavailable')
        db.delete(row);db.commit();return {'ok':True,'ai_calls':0}

    @app.post(base+'/preview')
    def preview(bid:int,data:ResourceRef,user=Depends(user_dependency),db=Depends(db_dependency)):
        return service.preview(boards.owned(bid,user,db,owner_only=True),data,db)

    @app.get(base+'/image/{sid}')
    def image(bid:int,sid:int,user=Depends(user_dependency),db=Depends(db_dependency)):
        row=service.source(boards.owned(bid,user,db,owner_only=True),'image',sid,db)
        return Response(service.image_bytes(row),media_type=row.attachment_mime,headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; sandbox"})

    @app.post(base+'/{kind}/{sid}/retry')
    def retry(bid:int,kind:Literal['document','dataset'],sid:int,user=Depends(user_dependency),db=Depends(db_dependency)):
        workspaces.lock_writes(user,db);board=boards.owned(bid,user,db,writable=True,owner_only=True);row=service.source(board,kind,sid,db)
        if kind=='document':
            from .document_api import Revision
            return endpoint('/documents/{did}/retry','POST')(sid,Revision(revision=row.revision),user,db)
        if not board.project_id:
            if row.status!='error' or row.attempts>=3:raise HTTPException(409,'Only failed datasets with fewer than three attempts can retry.')
            row.status,row.error='queued',None;workspaces.touch(row);db.commit();return service.info('dataset',row)
        from .dataset_api import Revision
        return endpoint('/projects/{pid}/data/datasets/{did}/retry','POST')(board.project_id,sid,Revision(revision=row.revision),user,db)

    @app.post(base+'/upload',status_code=201)
    async def upload(bid:int,file:UploadFile=File(...),user=Depends(user_dependency),db=Depends(db_dependency)):
        board=boards.owned(bid,user,db,writable=True,owner_only=True)
        if service.count_links(board,db)>=100:raise HTTPException(413,'Use at most 100 board resources')
        ext=Path(file.filename or '').suffix.lower()
        if ext not in ('.pdf','.docx','.txt','.md','.csv','.xlsx','.png','.jpg','.jpeg','.webp'):raise HTTPException(415,'Choose PDF, DOCX, TXT, Markdown, CSV, XLSX, PNG, JPEG or WebP')
        if ext in ('.csv','.xlsx'):
            from .dataset_api import upload_dataset
            row=upload_dataset(file,user,db,project_id=board.project_id,board=None if board.project_id else board);kind='dataset';sid=row['id']
        else:
            # Workspace-only files use an existing owned board conversation scope.
            conversation=db.scalar(select(Conversation).join(BoardConversation,BoardConversation.conversation_id==Conversation.id).where(BoardConversation.board_id==bid,Conversation.user_id==user.id).order_by(Conversation.id))
            if not conversation and (not board.project_id or ext in ('.png','.jpg','.jpeg','.webp')):
                workspaces.lock_writes(user,db);boards.owned(bid,user,db,writable=True,owner_only=True)
                conversation=Conversation(user_id=user.id,project_id=board.project_id,title='Resource uploads');db.add(conversation);db.flush();db.add(BoardConversation(board_id=bid,conversation_id=conversation.id));db.commit()
            if ext in ('.pdf','.docx','.txt','.md'):
                row=await endpoint('/documents','POST')(file,board.project_id,None if board.project_id else conversation.id,user,db);kind='document';sid=row['id']
            else:
                from .attachments import read_attachments
                fields=(await read_attachments([file],images_only=True))[0];await file.close()
                workspaces.lock_writes(user,db);board=boards.owned(bid,user,db,writable=True,owner_only=True)
                # Deduplicate original image bytes within this board's existing storage.
                existing=next((a for a in db.scalars(select(Attachment).join(Message).join(BoardConversation,BoardConversation.conversation_id==Message.conversation_id).where(BoardConversation.board_id==bid,Message.conversation_id.in_(select(Conversation.id).where(Conversation.user_id==user.id)))) if a.attachment_data==fields['attachment_data'] and a.attachment_mime==fields['attachment_mime']),None)
                if existing:sid=existing.id
                else:
                    from sqlalchemy import func
                    from .documents import MAX_OWNER_BYTES
                    total=db.scalar(select(func.coalesce(func.sum(Attachment.attachment_size),0)).join(Message).join(Conversation).where(Conversation.user_id==user.id))
                    if total+fields['attachment_size']>MAX_OWNER_BYTES:raise HTTPException(413,'Image storage limit reached (250 MB)')
                    message=Message(conversation_id=conversation.id,role='user',content='Canvas resource upload',active=0,attachments=[Attachment(**fields)])
                    db.add(message);db.flush();sid=message.attachments[0].id
                kind='image'
        workspaces.lock_writes(user,db);board=boards.owned(bid,user,db,writable=True,owner_only=True)
        result=service.link(board,kind,sid,db);db.commit();return result
