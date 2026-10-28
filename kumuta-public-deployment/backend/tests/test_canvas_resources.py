"""D7-6: real bounded parsers, private bytes, fake generation, disposable SQLite."""
import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from sqlalchemy import select, text
import test_canvas_generation as gen  # Configures disposable DB before application imports.
from app import canvas_resources as resources, documents, datasets, gemini, database
from app.document_models import Document, DocumentChunk, StoredFile
from app.dataset_models import Dataset
from app.canvas_resource_contract import ResourceRef
import test_boards as board_fixture
from test_boards import element, scene
from test_documents import pdf,docx
from test_datasets import xlsx


class ResourceTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=gen.GenerationAPITests.asyncSetUp
    asyncTearDown=gen.GenerationAPITests.asyncTearDown
    ok=gen.GenerationAPITests.ok
    board=gen.GenerationAPITests.board
    save=gen.GenerationAPITests.save
    create=gen.GenerationAPITests.create
    finish=gen.GenerationAPITests.finish
    added=gen.GenerationAPITests.added
    place=gen.GenerationAPITests.place
    artifact=gen.GenerationAPITests.artifact
    project=board_fixture.BoardAPITests.project

    async def prepare(self):
        patch.object(documents,'STORAGE',Path(self.temp.name)/'files').start()
        patch.object(documents,'SessionLocal',self.sessions).start()
        patch.object(datasets,'SessionLocal',self.sessions).start()
        p=await self.project();self.pid=p['id'];self.bid=(await self.board(project_id=self.pid))['id'];self.base=f'/boards/{self.bid}/resource-library'

    async def upload(self,name,data,mime='application/octet-stream',ready=True):
        row=await self.ok('POST',self.base+'/upload',201,files={'file':(name,data,mime)})
        if ready:
            while documents.process_next():pass
            while datasets.process_next():pass
            row=next(r for r in (await self.ok('GET',self.base))['items'] if r['kind']==row['kind'] and r['source_id']==row['source_id'])
        return row

    def ref(self,row,**kw):return {'schema_version':1,'kind':row['kind'],'source_id':row['source_id'],'fingerprint':row['fingerprint'],**kw}
    async def preview(self,ref,status=200):return await self.ok('POST',self.base+'/preview',status,json=ref)
    async def resolve(self,ref,**kw):return await self.ok('POST',f'/boards/{self.bid}/selection/resolve',json={'expected_revision':0,'resources':[ref],**kw})

    async def test_reuse_upload_link_unlink_and_private_originals(self):
        await self.prepare();row=await self.upload('research.pdf',pdf());same=await self.upload('again.pdf',pdf())
        # Different generated PDFs can have different metadata; reupload the exact bytes for dedup.
        raw=docx();a=await self.upload('plan.docx',raw);b=await self.upload('same.docx',raw);self.assertEqual(a['source_id'],b['source_id'])
        await self.ok('DELETE',f'{self.base}/document/{a["source_id"]}')
        await self.preview(self.ref(a),404)
        self.assertEqual((await self.ok('GET',f'/documents/{a["source_id"]}'))['status'],'ready')
        await self.ok('POST',self.base,201,json={'kind':'document','source_id':a['source_id']});await self.preview(self.ref(a))
        with self.sessions() as db:self.assertEqual(len(list(db.scalars(select(Document).where(Document.filename.in_(['plan.docx','same.docx']))))),1)
        self.assertEqual(self.calls,0)

    async def test_pdf_pages_docx_blocks_passages_and_scanned_state(self):
        await self.prepare();row=await self.upload('research.pdf',pdf());p=await self.preview(self.ref(row,page=2));self.assertIn('Security',p['items'][0]['text']);self.assertEqual(p['items'][0]['page'],2)
        ctx=await self.resolve(self.ref(row,page=2));self.assertIn('p. 2',ctx['resources'][0]['label']);self.assertNotIn('Architecture',json.dumps(ctx))
        await self.preview(self.ref(row,page=3),422)
        d=await self.upload('outline.docx',docx());p=await self.preview(self.ref(d));self.assertIsNone(p['items'][0]['page']);self.assertTrue(p['blocks'])
        bid=p['items'][0]['block_id'];p=await self.preview(self.ref(d,block_id=bid,start=0,end=7));self.assertEqual(p['items'][0]['text'],'Project')
        await self.preview(self.ref(d,page=1),422);await self.preview(self.ref(d,block_id=bid,end=999,start=0),422)
        table=await self.preview(self.ref(d,block_id=(await self.preview(self.ref(d)))['blocks'][-1]['block_id']));self.assertIn('SQLite',table['items'][0]['text'])
        from app.attachments import fitz
        blank=fitz.open();blank.new_page();r=await self.upload('scan.pdf',blank.tobytes());self.assertEqual(r['status'],'error');self.assertIn('text',r['error'].lower())

    async def test_csv_xlsx_sheets_ranges_and_types(self):
        await self.prepare();row=await self.upload('sales.csv',b'category,revenue,private\nA,10,secret\nB,20,hidden\nC,30,no\n')
        p=await self.preview(self.ref(row,row_start=1,row_end=2,columns=[1]));self.assertEqual(p['items'],[['20']]);self.assertEqual(p['columns'][0]['type'],'integer')
        c=await self.resolve(self.ref(row,row_start=1,row_end=2,columns=[1]));self.assertIn('B3:B3',c['resources'][0]['label']);self.assertNotIn('secret',json.dumps(c));self.assertNotIn('hidden',json.dumps(c))
        await self.preview(self.ref(row,row_start=2,row_end=4),422)
        book=await self.upload('book.xlsx',xlsx());p=await self.preview(self.ref(book,sheet='Codes',columns=[0],row_end=1));self.assertEqual(p['items'],[['001']]);self.assertEqual(p['columns'][0]['type'],'string')
        await self.preview(self.ref(book,sheet='Forged'),422)
        available=await self.ok('GET',self.base+'/available');self.assertTrue(any(r['kind']=='dataset' for r in available['items']))

    async def test_owner_scope_forgery_and_stale_refs_fail_closed(self):
        await self.prepare();row=await self.upload('sales.csv',b'a,b\nx,10\n')
        foreign=(await self.board())['id'];await self.ok('POST',f'/boards/{foreign}/resource-library',404,json={'kind':'dataset','source_id':row['source_id']})
        await self.preview({**self.ref(row),'source_id':999999},404)
        await self.preview({**self.ref(row),'fingerprint':'0'*64},409)
        await self.preview({**self.ref(row),'text':'forged'},422)
        account=(await self.client.post('/auth/signup',json={'email':'other-resources@example.com','password':'password123'})).json()
        r=await self.client.post(self.base+'/preview',headers={'Authorization':'Bearer '+account['token']},json=self.ref(row));self.assertEqual(r.status_code,404)
        await self.ok('DELETE',f'{self.base}/dataset/{row["source_id"]}');await self.preview(self.ref(row),404)
        self.assertEqual(self.calls,0)

    async def test_context_budgets_mixed_provenance_and_card_selection(self):
        await self.prepare();row=await self.upload('plan.docx',docx('x'*24500,False));p=await self.preview(self.ref(row));self.assertLess(len(p['items'][0]['text']),24500) # Existing chunker bounds each block.
        await self.save(self.bid,value=scene(element('resource',width=460,height=420),element('native',x=900),resources=[{'id':'r','anchor_id':'resource','reference':self.ref(row),'schema_version':1}]))
        context=await self.ok('POST',f'/boards/{self.bid}/selection/resolve',json={'expected_revision':1,'element_ids':['resource','native']});self.assertEqual(context['schema_version'],2);self.assertEqual(len(context['resources']),1);self.assertEqual([n['id'] for n in context['native']],['native'])
        # Card refs normalize before dispatch; stale checks must not duplicate evidence.
        self.response='Selected explanation';job=await self.create(mode='chat',selection={'expected_revision':1,'element_ids':['resource'],'action':'explain'});done=await self.finish();self.assertEqual(done['status'],'completed',done)
        huge=await self.upload('wide.csv',('value\n'+'z'*3999+'\n') .encode()*1)
        # Select too many repeated source blocks to overflow total context.
        with self.assertRaises(ValueError):ResourceRef(**self.ref(huge,row_start=0,row_end=101))
        large=await self.upload('large.csv',('value\n'+('\n'.join(['x'*3999]*10))+'\n').encode())
        await self.preview(self.ref(large,row_end=10),413)

    async def test_text_sources_and_atomic_resource_generation_preserve_evidence(self):
        await self.prepare();row=await self.upload('sales.csv',b'month,sales\nJan,10\nFeb,20\n');ref=self.ref(row,row_end=2)
        self.response='Sales explanation';cid=(await self.ok('POST',f'/boards/{self.bid}/conversations/new',201))['conversation_id']
        j=await self.create(mode='chat',conversation_id=cid,selection={'expected_revision':0,'resources':[ref],'action':'explain'});done=await self.finish();self.assertEqual(done['status'],'completed',done);self.assertEqual(done['engine'],'T');self.assertIn('sales.csv',done['selection']['resources'][0]['label'])
        self.response=gen.DIAGRAM;j=await self.create(request_key='resource-diagram',mode='diagram',selection={'expected_revision':0,'resources':[ref],'action':'modify'});await self.finish()
        placed=await self.place(j['artifact_id']);self.assertEqual(placed['revision'],1)
        # Unlink prevents subsequent acceptance of a pending resource-based proposal.
        j=await self.create(request_key='resource-stale',mode='diagram',selection={'expected_revision':1,'resources':[ref],'action':'modify'});await self.finish();await self.ok('DELETE',f'{self.base}/dataset/{row["source_id"]}')
        await self.place(j['artifact_id'],revision=1,status=404);self.assertEqual((await self.ok('GET',f'/boards/{self.bid}/scene'))['revision'],1)

    async def test_resource_unlink_before_dispatch_and_cancel_do_not_call_provider(self):
        await self.prepare();r=await self.upload('plan.docx',docx());ref=self.ref(r)
        j=await self.create(selection={'expected_revision':0,'resources':[ref],'action':'explain'});await self.ok('DELETE',f'{self.base}/document/{r["source_id"]}');done=await self.finish();self.assertEqual(done['status'],'failed');self.assertEqual(self.calls,0)
        await self.ok('POST',self.base,201,json={'kind':'document','source_id':r['source_id']})
        j=await self.create(request_key='cancel-resource',selection={'expected_revision':0,'resources':[ref],'action':'explain'});await self.ok('POST',f'/boards/{self.bid}/generations/{j["id"]}/cancel');self.assertEqual(self.calls,0)

    async def test_image_storage_reuse_dimensions_and_explicit_visual_consent(self):
        await self.prepare();from app.attachments import fitz
        pix=fitz.Pixmap(fitz.csRGB,fitz.IRect(0,0,3,2),False);pix.clear_with(255);raw=pix.tobytes('png')
        r=await self.upload('picture.png',raw,'image/png');r2=await self.upload('same.png',raw,'image/png');self.assertEqual(r['source_id'],r2['source_id']);self.assertEqual((r['width'],r['height']),(3,2));ref=self.ref(r)
        p=await self.preview(ref);self.assertEqual(p['resource']['width'],3)
        self.response='Image description';j=await self.create(mode='chat',selection={'expected_revision':0,'resources':[ref],'action':'explain','visual':False});done=await self.finish();self.assertFalse(done['selection']['visual_attached'])
        captured=[]
        class Fake:
            def __init__(self):self.aio=self;self.models=self
            async def __aenter__(self):return self
            async def __aexit__(self,*a):pass
            async def generate_content(self,**kwargs):captured.append(kwargs);return SimpleNamespace(text='Image description',usage_metadata=None)
        j=await self.create(request_key='image-consent',mode='chat',selection={'expected_revision':0,'resources':[ref],'action':'explain','visual':True})
        with patch.object(gemini,'client_for',return_value=Fake()):done=await self.finish()
        self.assertEqual(done['status'],'completed',done);self.assertTrue(done['selection']['visual_attached']);self.assertEqual(captured[0]['contents'][-1].parts[-1].inline_data.data,raw)
        await self.ok('DELETE',f'{self.base}/image/{r["source_id"]}');response=await self.client.get(f'{self.base}/image/{r["source_id"]}',headers=self.headers);self.assertEqual(response.status_code,404)

    async def test_processing_failure_retry_and_unsupported_formats(self):
        await self.prepare()
        for name,data,code in [('script.svg',b'<svg/>',415),('fake.png',b'bad',415),('bad.pdf',b'bad',422),('bad.xlsx',b'bad',422)]:
            await self.ok('POST',self.base+'/upload',code,files={'file':(name,data,'image/png' if name.endswith('.png') else 'application/octet-stream')})
        row=await self.upload('broken.docx',b'PK\x03\x04not-a-zip');self.assertEqual(row['status'],'error')
        await self.ok('POST',f'{self.base}/document/{row["source_id"]}/retry');self.assertEqual((await self.ok('GET',f'/documents/{row["source_id"]}'))['status'],'queued')
        while documents.process_next():pass
        await self.preview(self.ref(row),409)

    async def test_dataset_delete_cascade_and_backed_up_additive_migration(self):
        await self.prepare();row=await self.upload('sales.csv',b'a\nx\n')
        await self.ok('DELETE',f'/projects/{self.pid}/data/datasets/{row["source_id"]}',json={'revision':row['revision'],'confirmation':'DELETE'})
        self.assertEqual((await self.ok('GET',self.base))['items'],[]);await self.preview(self.ref(row),404)
        with self.engine.begin() as c:c.execute(text('DELETE FROM schema_migrations WHERE version>=20'))
        with patch.object(database,'engine',self.engine):database.migrate()
        backups=list(Path(self.temp.name).glob('*.bak'));self.assertTrue(backups);self.assertEqual(backups[-1].stat().st_mode&0o777,0o600)
        with self.engine.connect() as c:self.assertEqual(c.scalar(text('PRAGMA integrity_check')),'ok');self.assertEqual(c.scalar(text('SELECT max(version) FROM schema_migrations')),23)

    async def test_resource_image_upload_is_excluded_from_ordinary_ai_history(self):
        await self.prepare()
        from app.attachments import fitz
        from app.database import Attachment,Message
        pix=fitz.Pixmap(fitz.csRGB,fitz.IRect(0,0,2,2),False);pix.clear_with(255)
        row=await self.upload('private.png',pix.tobytes('png'),'image/png')
        with self.sessions() as db:
            message=db.get(Message,db.get(Attachment,row['source_id']).message_id)
            self.assertEqual(message.active,0)
        r=await self.upload('rows.csv',b'name,value\nselected,10\nunselected,900\n')
        context=await self.resolve(self.ref(r,row_end=1,columns=[1]))
        self.assertEqual(context['resources'][0]['content']['columns'],[{'name':'value','type':'integer'}])
        self.assertEqual(context['resources'][0]['content']['rows'],[['10']])

    async def test_unknown_citations_reprocessing_and_scene_reference_forgery(self):
        await self.prepare();r=await self.upload('outline.docx',docx());ref=self.ref(r)
        self.response='Evidence [R1]. Unknown [R99].'
        await self.create(mode='chat',selection={'expected_revision':0,'resources':[ref],'action':'explain'});done=await self.finish()
        self.assertEqual(done['reply_text'],'Evidence [R1]. Unknown [unavailable source].')
        frame={'schema_version':1,'id':'resource','anchor_id':'anchor','reference':{**ref,'source_id':999999}}
        await self.save(self.bid,value=scene(element('anchor',width=460,height=420),resources=[frame]),status=404)
        with self.sessions() as db:
            row=db.get(Document,r['source_id']);row.revision+=1;db.commit()
        await self.preview(ref,409)

    async def test_unlinked_historical_job_redacts_evidence_but_accepted_artifact_can_be_removed(self):
        await self.prepare();r=await self.upload('outline.docx',docx());ref=self.ref(r)
        j=await self.create(mode='diagram',selection={'expected_revision':0,'resources':[ref],'action':'modify'});await self.finish()
        await self.place(j['artifact_id'])
        copied=await self.ok('POST',f'/boards/{self.bid}/artifacts/{j["artifact_id"]}/duplicate',201,json={'request_key':'copy_resource_123','version':1})
        self.assertEqual(copied['versions'][0]['selection']['resources'][0]['filename'],'outline.docx')
        await self.ok('DELETE',f'{self.base}/document/{r["source_id"]}')
        old=await self.ok('GET',f'/boards/{self.bid}/generations/{j["id"]}')
        self.assertTrue(old['selection']['resources'][0]['unavailable']);self.assertNotIn('content',old['selection']['resources'][0])
        old=await self.artifact(j['artifact_id']);self.assertNotIn('content',old['versions'][0]['selection']['resources'][0])
        await self.place(j['artifact_id'],revision=1,operation='remove')

    async def test_v19_resource_migration_interruption_rolls_back_and_retries(self):
        await self.prepare()
        from app import migrations
        with self.engine.begin() as c:
            c.exec_driver_sql('DROP TABLE canvas_board_media');c.execute(text('DELETE FROM schema_migrations WHERE version>=20'))
        original=migrations.MIGRATIONS[20]
        def interrupted(c,t):original(c,t);raise RuntimeError('resource upgrade interrupted')
        with patch.object(database,'engine',self.engine),patch.dict(migrations.MIGRATIONS,{20:interrupted}):
            with self.assertRaisesRegex(RuntimeError,'resource upgrade interrupted'):database.migrate()
        with self.engine.connect() as c:
            self.assertEqual(c.scalar(text('SELECT max(version) FROM schema_migrations')),19)
            self.assertEqual(c.scalar(text("SELECT count(*) FROM sqlite_master WHERE name='canvas_board_media'")),0)
        with patch.object(database,'engine',self.engine):database.migrate()
        with self.engine.connect() as c:
            self.assertEqual(c.scalar(text('SELECT max(version) FROM schema_migrations')),23)
            self.assertEqual(c.scalar(text('PRAGMA integrity_check')),'ok')
            self.assertEqual(c.exec_driver_sql('PRAGMA foreign_key_check').all(),[])
        self.assertTrue(all(p.stat().st_mode&0o777==0o600 for p in Path(self.temp.name).glob('*.bak')))
