"""D7-1 contracts, each test using its own temporary SQLite database."""
import asyncio
import base64
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import test_api as fixture  # Configure a temporary legacy DB before importing main.
import httpx
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app import board_schemas, boards, database, document_chat, documents, main
from app.board_models import Board, BoardSceneRevision
from app.database import Conversation, User
from app.document_models import Document, DocumentChunk, StoredFile


def element(identity='shape', **values):
    return {'id': identity, 'type': 'rectangle', 'x': 1, 'y': 2, 'width': 100, 'height': 50,
            'angle': 0, 'version': 1, 'isDeleted': False, 'groupIds': [], **values}


def scene(*elements, **values):
    return {'type': 'excalidraw', 'version': 2, 'elements': list(elements), 'appState': {}, 'files': {}, **values}


class BoardAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TemporaryDirectory()
        self.engine = create_engine(f'sqlite:///{Path(self.temp.name)/"boards.db"}', connect_args={'check_same_thread': False, 'timeout': 15})
        @event.listens_for(self.engine, 'connect')
        def foreign_keys(connection, _): connection.execute('PRAGMA foreign_keys=ON')
        with patch.object(database, 'engine', self.engine): database.migrate()
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)
        def session():
            with self.sessions() as db: yield db
        main.app.dependency_overrides[main.db_session] = session
        self.provider = patch.object(main.gemini, 'client_for', side_effect=AssertionError('Board operation called provider')).start()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://test')
        account = await self.client.post('/auth/signup', json={'email': 'owner@example.com', 'password': 'password123'})
        self.assertEqual(account.status_code, 200, account.text)
        self.headers = {'Authorization': 'Bearer ' + account.json()['token']}
        self.wid = (await self.ok('GET', '/workspaces'))['items'][0]['id']

    async def asyncTearDown(self):
        self.provider.assert_not_called()
        patch.stopall()
        await self.client.aclose()
        main.app.dependency_overrides.pop(main.db_session, None)
        self.engine.dispose(); self.temp.cleanup()

    async def ok(self, method, path, status=200, **kwargs):
        response = await self.client.request(method, path, headers=self.headers, **kwargs)
        self.assertEqual(response.status_code, status, response.text)
        if path.startswith('/boards'):
            self.assertEqual(response.headers.get('Cache-Control'), 'private, no-store')
        return response.json()

    async def board(self, **values):
        return await self.ok('POST', '/boards', 201, json={'workspace_id': self.wid, 'title': 'Board', **values})

    async def project(self, wid=None):
        return await self.ok('POST', f'/workspaces/{wid or self.wid}/projects', 201, json={'name': 'Project'})

    async def conversation(self, pid=None):
        return (await self.ok('POST', '/conversations', json={'project_id': pid}))['id']

    def document(self, *, pid=None, cid=None, content='needle shared evidence', ready=True):
        with self.sessions() as db:
            owner = db.scalar(select(User).where(User.email == 'owner@example.com'))
            stored = StoredFile(storage_key=__import__('uuid').uuid4().hex); db.add(stored); db.flush()
            row = Document(user_id=owner.id, project_id=pid, conversation_id=cid,
                scope_key=f'project:{pid}' if pid else f'conversation:{cid}', file_id=stored.id,
                filename='reference.txt', mime='text/plain', size=len(content), sha256=__import__('uuid').uuid4().hex*2,
                status='ready' if ready else 'queued')
            db.add(row); db.flush(); db.add(DocumentChunk(document_id=row.id, ordinal=0, section='', content=content)); db.commit()
            return row.id

    async def save(self, bid, expected=0, value=None, status=200):
        return await self.ok('PUT', f'/boards/{bid}/scene', status, json={'expected_revision': expected, 'scene': value or scene(element())})

    async def test_board_crud_archive_restore_and_pagination(self):
        row = await self.board(title='  First board  '); bid = row['id']
        self.assertEqual(row['title'], 'First board'); self.assertEqual(row['current_revision'], 0)
        self.assertEqual((await self.ok('GET', f'/boards/{bid}'))['workspace_id'], self.wid)
        await self.board()
        self.assertTrue((await self.ok('GET', f'/boards?workspace_id={self.wid}&limit=1'))['has_more'])
        await self.ok('PATCH', f'/boards/{bid}', json={'title': 'Renamed', 'status': 'archived'})
        self.assertEqual(len((await self.ok('GET', f'/boards?workspace_id={self.wid}&status=archived'))['items']), 1)
        await self.save(bid, status=409)
        await self.ok('GET', f'/boards/{bid}/scene')
        await self.ok('PATCH', f'/boards/{bid}', json={'status': 'active'})
        await self.save(bid)
        for payload in ({}, {'title': ''}, {'status': None}, {'workspace_id': self.wid}, {'owner_id': 1}):
            await self.ok('PATCH', f'/boards/{bid}', 422, json=payload)

    async def test_authentication_and_cross_user_every_endpoint(self):
        p = await self.project(); board = await self.board(project_id=p['id']); bid = board['id']
        await self.save(bid)
        routes = [('GET', f'/boards/{bid}', None), ('PATCH', f'/boards/{bid}', {'title':'Stolen'}),
                  ('GET', f'/boards/{bid}/scene', None), ('PUT', f'/boards/{bid}/scene', {'expected_revision':1,'scene':scene()}),
                  ('GET', f'/boards/{bid}/revisions', None), ('GET', f'/boards/{bid}/revisions/1', None),
                  ('POST', f'/boards/{bid}/revisions/1/restore', {'expected_revision':1}),
                  ('GET', f'/boards/{bid}/resources', None), ('POST', f'/boards/{bid}/resources', {'document_id':1}),
                  ('DELETE', f'/boards/{bid}/resources/1', None), ('GET', f'/boards/{bid}/conversations', None),
                  ('POST', f'/boards/{bid}/conversations', {'conversation_id':1}), ('DELETE', f'/boards/{bid}/conversations/1', None)]
        other = (await self.client.post('/auth/signup', json={'email':'other@example.com','password':'password123'})).json()
        owner_headers = self.headers
        for method, path, body in routes:
            unauth = await self.client.request(method, path, **({'json':body} if body else {}))
            self.assertEqual(unauth.status_code, 401, unauth.text)
            self.headers = {'Authorization': 'Bearer ' + other['token']}
            await self.ok(method, path, 404, **({'json':body} if body else {}))
        await self.ok('GET', f'/boards?workspace_id={self.wid}', 404)
        await self.ok('POST', '/boards', 404, json={'workspace_id':self.wid})
        self.headers = owner_headers
        await self.ok('GET', f'/boards/{bid}')

    async def test_same_owner_workspace_project_boundaries_and_archived_project(self):
        p = await self.project()
        ws = await self.ok('POST', '/workspaces', 201, json={'name':'Second'})
        await self.ok('POST', '/boards', 404, json={'workspace_id':ws['id'],'project_id':p['id']})
        await self.ok('POST', '/boards', 404, json={'workspace_id':self.wid,'project_id':999999})
        board = await self.board(project_id=p['id']); bid = board['id']
        await self.ok('GET', f'/boards?workspace_id={ws["id"]}&project_id={p["id"]}', 404)
        await self.ok('PATCH', f'/projects/{p["id"]}', json={'revision':1,'archived':True})
        await self.ok('GET', f'/boards/{bid}')
        await self.save(bid, status=409)
        await self.ok('POST', '/boards', 409, json={'workspace_id':self.wid,'project_id':p['id']})

    async def test_scene_history_restore_and_conflicts(self):
        bid = (await self.board())['id']
        self.assertEqual((await self.ok('GET', f'/boards/{bid}/scene'))['revision'], 0)
        first = await self.save(bid, value=scene(element('original')))
        await self.save(bid, 0, status=409)
        await self.save(bid, 1, scene(element('next')))
        restored = await self.ok('POST', f'/boards/{bid}/revisions/1/restore', json={'expected_revision':2})
        self.assertEqual(restored['revision'], 3); self.assertEqual(restored['restored_from'], 1)
        self.assertEqual(restored['scene'], first['scene'])
        self.assertEqual((await self.ok('GET', f'/boards/{bid}/revisions/1'))['scene'], first['scene'])
        self.assertEqual((await self.ok('GET', f'/boards/{bid}/scene'))['revision'], 3)
        history = await self.ok('GET', f'/boards/{bid}/revisions?limit=2')
        self.assertTrue(history['has_more']); self.assertEqual([r['revision'] for r in history['items']], [3,2])
        await self.ok('POST', f'/boards/{bid}/revisions/1/restore', 409, json={'expected_revision':2})
        await self.ok('POST', f'/boards/{bid}/revisions/999/restore', 404, json={'expected_revision':3})

    async def test_two_concurrent_saves_have_one_winner(self):
        bid = (await self.board())['id']
        responses = await asyncio.gather(*(self.client.put(f'/boards/{bid}/scene', headers=self.headers,
            json={'expected_revision':0, 'scene':scene(element(str(i)))}) for i in range(2)))
        self.assertEqual(sorted(r.status_code for r in responses), [200,409])
        self.assertEqual(len((await self.ok('GET', f'/boards/{bid}/revisions'))['items']), 1)

    async def test_failed_revision_insert_rolls_back_board_pointer(self):
        bid = (await self.board())['id']
        def fail(*_): raise RuntimeError('Interrupted save')
        event.listen(BoardSceneRevision, 'before_insert', fail)
        try:
            with self.assertRaisesRegex(Exception, 'Interrupted save'): await self.save(bid)
        finally: event.remove(BoardSceneRevision, 'before_insert', fail)
        self.assertEqual((await self.ok('GET', f'/boards/{bid}'))['current_revision'], 0)
        self.assertEqual((await self.ok('GET', f'/boards/{bid}/revisions'))['items'], [])
        await self.save(bid)

    async def test_ids_bindings_images_and_ephemeral_state(self):
        bid = (await self.board())['id']
        png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=')
        value = scene(element('shape', groupIds=['group'], boundElements=[{'id':'arrow','type':'arrow'}]),
            element('arrow', type='arrow', points=[[0,0],[20,20]], startBinding={'elementId':'shape','focus':0,'gap':1}),
            element('image', type='image', fileId='file', scale=[1,-1]),
            appState={'viewBackgroundColor':'#ffffff','selectedElementIds':{'shape':True},'collaborators':{'secret':'private'},'activeTool':{'type':'rectangle'}},
            files={'file':{'id':'file','mimeType':'image/png','dataURL':'data:image/png;base64,'+base64.b64encode(png).decode(),'created':1}})
        result = await self.save(bid, value=value)
        self.assertEqual(result['scene']['elements'], value['elements'])
        self.assertEqual(result['scene']['files'], value['files'])
        self.assertEqual(result['scene']['appState'], {'viewBackgroundColor':'#ffffff'})
        self.assertEqual((await self.ok('GET', f'/boards/{bid}/scene'))['scene'], result['scene'])

    async def test_malformed_scenes_are_rejected_without_history(self):
        bid = (await self.board())['id']
        invalid = [scene(element(),element()), scene(element(type='iframe')), scene(element(type='selection')),
            scene(element(x='nan')), scene(element(width=-1)), scene(element(customData={'html':'<script>'})),
            scene(element(link='javascript:alert(1)')), scene(element(type='image',fileId='missing',scale=[1,1])),
            scene(element(frameId='missing')), scene(element(type='arrow',points='bad')),
            scene(element(type='text')), scene(element(locked='true')), scene(element(roundness={'type':99})),
            scene(element(type=[])), scene(element(strokeColor=None)), scene(element(version=-1)),
            scene(element(), files={'bad':{'id':'bad','mimeType':'image/svg+xml','dataURL':'data:image/svg+xml;base64,PHN2Zz4='}}),
            scene(element(), files={'bad':{'id':'bad','mimeType':'image/png','dataURL':'https://localhost/secret'}}),
            scene(element(), files={'bad':{'id':'bad','mimeType':'image/png','dataURL':'data:image/png;base64,YmFk'}})]
        for value in invalid: await self.save(bid, value=value, status=422)
        for extra in ({'schema_version':2}, {'schema_version':True}, {'schema_version':1.0}, {'expected_revision':True}, {'expected_revision':-1}):
            await self.ok('PUT', f'/boards/{bid}/scene', 422, json={'expected_revision':0,'scene':scene(),**extra})
        for raw in (b'{', b'{"expected_revision":0,"scene":{"elements":[{"id":"a","type":"rectangle","x":NaN,"y":0,"width":1,"height":1}]}}', b'['*1100):
            response = await self.client.put(f'/boards/{bid}/scene', headers={**self.headers,'Content-Type':'application/json'}, content=raw)
            self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual((await self.ok('GET', f'/boards/{bid}/revisions'))['items'], [])

    async def test_body_scene_nesting_element_and_storage_limits(self):
        bid = (await self.board())['id']
        response = await self.client.put(f'/boards/{bid}/scene', headers=self.headers, content=b'x'*(board_schemas.MAX_REQUEST_BYTES+1))
        self.assertEqual(response.status_code,413)
        async def chunks():
            for _ in range(9): yield b'x'*(1024*1024)
        response = await self.client.put(f'/boards/{bid}/scene', headers=self.headers, content=chunks())
        self.assertEqual(response.status_code,413)
        with patch.object(board_schemas, 'MAX_SCENE_BYTES', 100): await self.save(bid, status=413)
        with patch.object(boards, 'MAX_OWNER_SCENE_BYTES', 1): await self.save(bid, status=413)
        deep = {}; cursor = deep
        for _ in range(22): cursor['nested'] = {}; cursor = cursor['nested']
        await self.save(bid, value=scene(appState=deep), status=422)
        await self.save(bid, value=scene(*[element(str(i)) for i in range(10001)]), status=422)
        await self.save(bid)
        with patch.object(boards, 'MAX_REVISIONS', 1): await self.save(bid, 1, status=413)

    async def test_conversation_and_resource_scope_links(self):
        p = await self.project(); other = await self.project(); bid = (await self.board(project_id=p['id']))['id']
        cid = await self.conversation(p['id']); wrong = await self.conversation(other['id'])
        for bad in (wrong,999999): await self.ok('POST', f'/boards/{bid}/conversations',404,json={'conversation_id':bad})
        await self.ok('POST', f'/boards/{bid}/conversations',201,json={'conversation_id':cid})
        await self.ok('POST', f'/boards/{bid}/conversations',201,json={'conversation_id':cid})
        second = (await self.board(project_id=p['id']))['id']
        await self.ok('POST', f'/boards/{second}/conversations',409,json={'conversation_id':cid})
        await self.ok('PATCH', f'/conversations/{cid}/project',409,json={'expected_project_id':p['id'],'project_id':other['id']})
        did = self.document(pid=p['id']); cdid = self.document(cid=cid); bad = self.document(pid=other['id']); unlinked = self.document(cid=await self.conversation(p['id']))
        for invalid in (bad,unlinked,999999): await self.ok('POST',f'/boards/{bid}/resources',404,json={'document_id':invalid})
        for valid in (did,cdid): await self.ok('POST',f'/boards/{bid}/resources',201,json={'document_id':valid})
        await self.ok('POST',f'/boards/{bid}/resources',201,json={'document_id':did})
        self.assertEqual({r['document_id'] for r in (await self.ok('GET',f'/boards/{bid}/resources'))['items']},{did,cdid})
        self.assertEqual(len((await self.ok('GET',f'/boards/{bid}/conversations'))['items']),1)
        await self.ok('DELETE',f'/boards/{bid}/conversations/{cid}')
        self.assertEqual([r['document_id'] for r in (await self.ok('GET',f'/boards/{bid}/resources'))['items']],[did])
        await self.ok('DELETE',f'/boards/{bid}/resources/{did}')
        with self.sessions() as db: self.assertIsNotNone(db.get(Document,did));self.assertIsNotNone(db.get(Conversation,cid))

    async def test_board_chat_document_allowlist_filters_before_retrieval(self):
        p = await self.project(); bid = (await self.board(project_id=p['id']))['id']; cid = await self.conversation(p['id'])
        visible = self.document(pid=p['id']); hidden = self.document(pid=p['id'])
        await self.ok('POST',f'/boards/{bid}/conversations',201,json={'conversation_id':cid})
        async def evidence():
            with self.sessions() as db:
                c = db.get(Conversation,cid); u = db.get(User,c.user_id)
                return await document_chat.context(c,u,'needle',[],'search',db,None,None)
        self.assertEqual((await evidence())[1],[])
        await self.ok('POST',f'/boards/{bid}/resources',201,json={'document_id':visible})
        self.assertEqual({s['document_id'] for s in (await evidence())[1]},{visible})
        self.assertEqual([r['id'] for r in (await self.ok('GET',f'/documents?conversation_id={cid}'))['items']],[visible])
        self.assertEqual({r['document_id'] for r in (await self.ok('GET',f'/documents/search?conversation_id={cid}&q=needle'))['items']},{visible})
        with self.sessions() as db:
            c = db.get(Conversation,cid); u = db.get(User,c.user_id)
            with self.assertRaises(main.HTTPException) as error: documents.authorized_documents(c,u,db,[hidden])
            self.assertEqual(error.exception.status_code,404)
        await self.ok('DELETE',f'/boards/{bid}/resources/{visible}')
        self.assertEqual((await evidence())[1],[])
        # Existing project-wide retrieval remains available outside board chat.
        self.assertEqual(len((await self.ok('GET',f'/documents/search?project_id={p["id"]}&q=needle'))['items']),2)

    async def test_cross_user_sources_and_live_source_revocation(self):
        p = await self.project(); bid = (await self.board(project_id=p['id']))['id']; cid = await self.conversation(p['id'])
        did = self.document(cid=cid)
        await self.ok('POST',f'/boards/{bid}/conversations',201,json={'conversation_id':cid})
        await self.ok('POST',f'/boards/{bid}/resources',201,json={'document_id':did})
        other = (await self.client.post('/auth/signup',json={'email':'foreign@example.com','password':'password123'})).json()
        headers = {'Authorization':'Bearer '+other['token']}
        wid = (await self.client.get('/workspaces',headers=headers)).json()['items'][0]['id']
        foreign_board = (await self.client.post('/boards',headers=headers,json={'workspace_id':wid})).json()['id']
        for kind, body in (('resources',{'document_id':did}),('conversations',{'conversation_id':cid})):
            r = await self.client.post(f'/boards/{foreign_board}/{kind}',headers=headers,json=body)
            self.assertEqual(r.status_code,404,r.text)
        with self.sessions() as db:
            row = db.get(Conversation,cid);row.project_id=None;db.commit()
        self.assertEqual((await self.ok('GET',f'/boards/{bid}/resources'))['items'],[])
        await self.ok('GET',f'/boards/{bid}/conversations',404)

    async def test_database_immutability_scope_constraints_and_cascades(self):
        p = await self.project(); bid = (await self.board(project_id=p['id']))['id']; await self.save(bid)
        for sql in ('UPDATE canvas_scene_revisions SET scene_json=\'{}\'', 'DELETE FROM canvas_scene_revisions'):
            with self.sessions() as db:
                with self.assertRaises(IntegrityError): db.execute(text(sql));db.commit()
        ws = await self.ok('POST','/workspaces',201,json={'name':'Other'})
        with self.sessions() as db:
            owner = db.scalar(select(User).where(User.email=='owner@example.com'))
            db.add(Board(owner_id=owner.id,workspace_id=ws['id'],project_id=p['id'],title='Invalid'))
            with self.assertRaises(IntegrityError): db.commit()
        await self.ok('DELETE',f'/projects/{p["id"]}',json={'revision':1,'confirm_name':'Project'})
        with self.sessions() as db:
            self.assertIsNone(db.get(Board,bid));self.assertIsNone(db.get(BoardSceneRevision,(bid,1)))
            self.assertEqual(db.execute(text('PRAGMA foreign_key_check')).all(),[])
