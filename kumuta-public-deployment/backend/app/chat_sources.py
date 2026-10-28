"""Conversation presentation adapter over private datasets and verified analytics."""
import json
from fastapi import Depends, File, HTTPException, UploadFile
from pydantic import Field
from sqlalchemy import select
from .database import Conversation, User
from .dataset_models import Dataset
from .data_schemas import Strict, AnalysisSpec, Question
from . import workspaces, datasets, dataset_api, data_ai
from .data_analysis_api import result


class SheetRequest(Strict):
    dataset_id: int = Field(gt=0)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    sheet: str | None = Field(None, max_length=120)
    spec: AnalysisSpec | None = None


def conversation_owned(cid, user, db, writable=False):
    row = db.scalar(select(Conversation).where(Conversation.id == cid, Conversation.user_id == user.id))
    if row is None:
        raise HTTPException(404, 'Conversation not found')
    from .boards import linked_board
    if linked_board(cid, user, db):
        raise HTTPException(422, 'Use Canvas Resources for board conversation sources.')
    if row.project_id is not None:
        workspaces.owned_project(row.project_id, user, db, writable=writable)
    return row


def owned(cid, did, user, db):
    conversation_owned(cid, user, db)
    row = db.scalar(select(Dataset).where(Dataset.id == did, Dataset.owner_id == user.id, Dataset.conversation_id == cid))
    if row is None:
        raise HTTPException(404, 'Dataset not found in this conversation.')
    return row


def parse_requests(raw):
    try:
        if len(raw) > 16000: raise ValueError()
        values = json.loads(raw)
        if not isinstance(values, list) or len(values) > 4: raise ValueError()
        requests = [SheetRequest.model_validate(v) for v in values]
        if len({(v.dataset_id, v.sheet) for v in requests}) != len(requests): raise ValueError()
        return requests
    except (ValueError, TypeError):
        raise HTTPException(422, 'Choose up to four distinct dataset worksheets with current fingerprints.') from None


def check_access(cid, item, user, db, verify_file=False):
    row = owned(cid, item.dataset_id, user, db)
    if row.sha256 != item.sha256:
        raise HTTPException(409, 'Dataset fingerprint changed. Select the source again.')
    if row.status != 'ready':
        raise HTTPException(409, 'Wait for the selected worksheet to finish processing.')
    if item.sheet is not None and item.sheet not in {s['name'] for s in json.loads(row.metadata_json)}:
        raise HTTPException(422, 'Worksheet unavailable.')
    if verify_file:
        from .canvas_resources import checked_file
        checked_file(row, db)
    return row


def checked(cid, item, user, db):
    row = check_access(cid, item, user, db)
    data = datasets.sheet_data(row, item.sheet, db)
    return row, data


async def prepare(cid, requests, query, user, db, check_active):
    outputs = []
    for item in requests:
        row, data = checked(cid, item, user, db)
        if item.spec is not None:
            spec = item.spec
            if spec.sheet not in (None, data['name']):
                raise HTTPException(422, 'Analysis selected a different worksheet.')
        else:
            db.commit()
            await check_active()
            spec, _ = await data_ai.interpret(Question(dataset_id=row.id, sheet=data['name'], question=query[:2000] or 'Describe the worksheet columns and missing values.'), data, user, conversation_id=cid)
            await check_active()
            db.expire_all()
            row, fresh = checked(cid, item, user, db)
            data = fresh
        output = result(row, data, spec.model_copy(update={'sheet': data['name'], 'offset': 0}))
        output['source_sha256'] = row.sha256
        outputs.append(output)
    computed = {'schema_version': 1, 'results': outputs, 'provider_calls': 0,
                'combination': 'separate attributed worksheets; no implicit joins'}
    if len(json.dumps(computed, ensure_ascii=False).encode()) > 64000:
        raise HTTPException(413, 'Verified analysis exceeds 64000 bytes. Narrow the analysis.')
    return computed


def register(app, user_dependency, db_dependency):
    @app.post('/conversations/{cid}/datasets', status_code=201)
    def upload(cid: int, file: UploadFile = File(...), user: User = Depends(user_dependency), db=Depends(db_dependency)):
        conversation_owned(cid, user, db, writable=True)
        return dataset_api.upload_dataset(file, user, db, conversation_id=cid)

    @app.get('/conversations/{cid}/datasets')
    def listing(cid: int, user: User = Depends(user_dependency), db=Depends(db_dependency)):
        conversation_owned(cid, user, db)
        return {'items': [datasets.view(r) for r in db.scalars(select(Dataset).where(Dataset.owner_id == user.id, Dataset.conversation_id == cid).order_by(Dataset.id))], 'ai_calls': 0}

    @app.get('/conversations/{cid}/datasets/{did}')
    def detail(cid: int, did: int, user: User = Depends(user_dependency), db=Depends(db_dependency)):
        return datasets.view(owned(cid, did, user, db))

    @app.get('/conversations/{cid}/datasets/{did}/schema')
    def schema(cid: int, did: int, sheet: str | None = None, user: User = Depends(user_dependency), db=Depends(db_dependency)):
        data = datasets.sheet_data(owned(cid, did, user, db), sheet, db)
        return {k: v for k, v in data.items() if k != 'rows'} | {'ai_calls': 0}

    @app.post('/conversations/{cid}/datasets/{did}/retry')
    def retry(cid: int, did: int, user: User = Depends(user_dependency), db=Depends(db_dependency)):
        conversation_owned(cid, user, db, writable=True)
        workspaces.lock_writes(user, db)
        row = owned(cid, did, user, db)
        if row.status != 'error' or row.attempts >= 3:
            raise HTTPException(409, 'Only failed datasets with fewer than three attempts can retry.')
        row.status, row.error = 'queued', None
        workspaces.touch(row); db.commit()
        return datasets.view(row)

    @app.post('/conversations/{cid}/datasets/{did}/analyze')
    def analyze(cid: int, did: int, spec: AnalysisSpec, user: User = Depends(user_dependency), db=Depends(db_dependency)):
        row = owned(cid, did, user, db)
        return result(row, datasets.sheet_data(row, spec.sheet, db), spec)
