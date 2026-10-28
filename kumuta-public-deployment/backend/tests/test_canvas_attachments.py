"""D7-7.1: real private upload/parser/RAG reuse with fake provider only."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from app import documents, datasets, gemini
import test_canvas_resources as resources
from test_canvas_resources import docx, pdf, xlsx
import test_canvas_intelligence as intelligence
from test_canvas_generation import WIDGET, DIAGRAM


class AttachmentTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=resources.ResourceTests.asyncSetUp
    asyncTearDown=resources.ResourceTests.asyncTearDown
    ok=resources.ResourceTests.ok
    board=resources.ResourceTests.board
    save=resources.ResourceTests.save
    create=resources.ResourceTests.create
    finish=resources.ResourceTests.finish
    project=resources.ResourceTests.project
    prepare=resources.ResourceTests.prepare
    upload=resources.ResourceTests.upload
    ref=resources.ResourceTests.ref
    preview=resources.ResourceTests.preview
    request=intelligence.IntelligenceTests.request

    async def test_all_formats_remain_private_authorized_resources_without_provider_calls(self):
        await self.prepare()
        for name,data in [('research.pdf',pdf()),('outline.docx',docx()),('notes.txt',b'SQLite architecture evidence.'),('guide.md',b'# SQLite\nPrivate architecture evidence.'),('sales.csv',b'month,value\nJan,10\n'),('book.xlsx',xlsx())]:
            r=await self.upload(name,data);self.assertEqual(r['status'],'ready',r)
            p=await self.preview(self.ref(r));self.assertEqual(p['resource']['source_id'],r['source_id'])
        from app.attachments import fitz
        pix=fitz.Pixmap(fitz.csRGB,fitz.IRect(0,0,2,2),False);pix.clear_with(255)
        for ext,mime in [('png','image/png'),('jpg','image/jpeg')]:
            r=await self.upload('image.'+ext,pix.tobytes(ext),mime);self.assertEqual(r['status'],'ready')
        # WebP uses the existing real decoder, with a valid tiny synthetic fixture.
        import base64
        webp=base64.b64decode('UklGRiQAAABXRUJQVlA4IBgAAAAwAQCdASoCAAIAAUAmJaQAA3AA/vz0AAA=')
        error=await self.ok('POST',self.base+'/upload',415,files={'file':('image.webp',webp,'image/webp')});self.assertIn('WebP decoding is unavailable',error['detail'])
        self.assertEqual(self.calls,0)

    async def test_text_ingestion_dedup_processing_and_binary_rejection(self):
        await self.prepare();raw=b'SQLite authorized text evidence.'
        r=await self.upload('notes.txt',raw,ready=False);self.assertEqual(r['status'],'queued')
        await self.preview(self.ref(r),409)
        while documents.process_next():pass
        ready=await self.upload('same.txt',raw);self.assertEqual(ready['source_id'],r['source_id'])
        for name,data,code in [('binary.txt',b'\0bad',422),('encoding.md',b'\xff',422),('macro.xlsm',b'PKbad',415),('archive.zip',b'PKbad',415),('script.exe',b'MZ',415)]:
            await self.ok('POST',self.base+'/upload',code,files={'file':(name,data,'application/octet-stream')})
        other=(await self.board())['id']
        await self.ok('POST',f'/boards/{other}/resource-library/preview',404,json=self.ref(ready))
        self.assertEqual(self.calls,0)

    async def test_document_openui_and_ordinary_rag_share_lifecycle(self):
        await self.prepare();r=await self.upload('study.md',b'# SQLite\nSQLite FTS5 retrieves authorized evidence for learning.')
        request=self.request([self.ref(r)],query='SQLite')
        self.response=WIDGET
        request['action']='modify'
        j=await self.create(mode='ui',selection=request);done=await self.finish()
        self.assertEqual(done['status'],'completed',done);self.assertEqual(done['engine'],'B');self.assertEqual(done['selection']['retrieval']['method'],'fts5-bm25')
        self.response='SQLite evidence [R99999999]'
        await self.create(request_key='attached-chat',mode='chat',selection=self.request([self.ref(r)],query='SQLite'));done=await self.finish()
        self.assertEqual(done['status'],'completed',done);self.assertIn('[unavailable source]',done['reply_text'])

    async def test_explicit_chat_image_can_accompany_rag_but_requires_visual_flag(self):
        await self.prepare();r=await self.upload('notes.txt',b'SQLite security evidence.')
        cid=(await self.ok('POST',f'/boards/{self.bid}/conversations/new',201))['conversation_id']
        from app.attachments import fitz
        pix=fitz.Pixmap(fitz.csRGB,fitz.IRect(0,0,2,2),False);pix.clear_with(255)
        raw=pix.tobytes('png');request=self.request([self.ref(r)],query='SQLite');request['visual']=True
        import json
        body={'request_key':'mixed-image-rag','prompt':'Explain SQLite and this image','mode':'chat','conversation_id':cid,'selection':request}
        j=await self.ok('POST',f'/boards/{self.bid}/generations',201,data={'request':json.dumps(body)},files={'attachments':('diagram.png',raw,'image/png')})
        self.job=j;done=await self.finish();self.assertEqual(done['status'],'completed',done);self.assertTrue(done['selection']['visual_attached']);self.assertEqual(len(done['attachments']),1)
        request['visual']=False;body['request_key']='unconfirmed-image'
        await self.ok('POST',f'/boards/{self.bid}/generations',422,data={'request':json.dumps(body)},files={'attachments':('diagram.png',raw,'image/png')})

    async def test_mixed_document_comparison_includes_recomputed_verified_totals(self):
        await self.prepare()
        document=await self.upload('claims.txt',b'SQLite sales report claims revenue is 80.')
        dataset=await self.upload('sales.csv',b'category,revenue\nA,10\nA,20\nB,30\n')
        tasks=[{'source_id':dataset['source_id'],'spec':{'metrics':[{'op':'sum','column':'revenue','alias':'Revenue'}],'chart':'table'}}]
        request=self.request([self.ref(document),self.ref(dataset)],'compare',query='SQLite revenue',analyses=tasks)
        self.response='The worksheet total is 60; the report claims 80.'
        await self.create(mode='chat',selection=request);done=await self.finish()
        self.assertEqual(done['status'],'completed',done)
        self.assertEqual(done['selection']['verified_analysis']['results'][0]['rows'],[['60']])
        self.assertTrue(any(r['reference']['kind']=='document' for r in done['selection']['resources']))
        self.assertEqual(self.calls,1)

    async def test_attached_documents_keep_local_auto_chat_diagram_and_ui_routing(self):
        await self.prepare();r=await self.upload('routing.txt',b'SQLite architecture evidence for local diagrams and learning widgets.')
        for key,prompt,reply,engine in [('auto-question','Explain SQLite architecture','Explanation','T'),('auto-diagram','Create a SQLite architecture diagram',DIAGRAM,'A'),('auto-widget','Create a SQLite learning widget',WIDGET,'B')]:
            self.response=reply
            await self.create(request_key=key,prompt=prompt,mode='auto',selection=self.request([self.ref(r)],query='SQLite'))
            done=await self.finish();self.assertEqual(done['status'],'completed',done);self.assertEqual(done['engine'],engine)
        self.assertEqual(self.calls,3)

    async def test_workspace_board_accepts_spreadsheets_and_keeps_them_board_private(self):
        await self.prepare()
        self.bid=(await self.board())['id'];self.base=f'/boards/{self.bid}/resource-library'
        for filename,raw in [('sales.csv',b'category,revenue\nA,10\nB,20\n'),('book.xlsx',xlsx())]:
            row=await self.upload(filename,raw)
            self.assertEqual(row['status'],'ready',row)
            await self.preview(self.ref(row))
            same=await self.upload(filename,raw);self.assertEqual(row['source_id'],same['source_id'])
            other=(await self.board())['id']
            await self.ok('POST',f'/boards/{other}/resource-library',404,json={'kind':'dataset','source_id':row['source_id']})
            await self.ok('POST',f'/boards/{other}/resource-library/preview',404,json=self.ref(row))
            await self.ok('GET',f'/projects/{self.pid}/data/datasets/{row["source_id"]}',404)
            self.assertTrue(any(r['source_id']==row['source_id'] for r in (await self.ok('GET',self.base+'/available'))['items']))
        dataset=await self.upload('totals.csv',b'category,revenue\nA,10\nA,20\nB,30\n')
        tasks=[{'source_id':dataset['source_id'],'spec':{'metrics':[{'op':'sum','column':'revenue','alias':'Revenue'}],'chart':'table'}}]
        request=self.request([self.ref(dataset)],'ask',query='Total revenue',analyses=tasks)
        self.response='Verified total revenue is 60.'
        await self.create(mode='chat',selection=request);done=await self.finish()
        self.assertEqual(done['status'],'completed',done)
        self.assertEqual(done['selection']['verified_analysis']['results'][0]['rows'],[['60']])

    async def test_workspace_board_dataset_retry_and_document_formats(self):
        await self.prepare();self.bid=(await self.board())['id'];self.base=f'/boards/{self.bid}/resource-library'
        for filename,raw in [('notes.txt',b'SQLite private board notes.'),('guide.md',b'# SQLite\nPrivate guide.'),('report.pdf',pdf()),('plan.docx',docx())]:
            self.assertEqual((await self.upload(filename,raw))['status'],'ready')
        row=await self.upload('broken.xlsx',b'PK\x03\x04broken');self.assertEqual(row['status'],'error')
        retried=await self.ok('POST',f'{self.base}/dataset/{row["source_id"]}/retry')
        self.assertEqual(retried['status'],'queued')
        while datasets.process_next():pass
        self.assertEqual(self.calls,0)

    async def test_populated_v20_dataset_migration_preserves_links_and_rolls_back(self):
        from sqlalchemy import text
        from sqlalchemy.schema import CreateTable
        from app import database,migrations
        from app.dataset_models import Dataset
        from app.board_models import BoardMediaLink
        await self.prepare();row=await self.upload('keep.csv',b'category,revenue\nA,10\n')
        with self.engine.begin() as c:
            records=c.execute(text('SELECT * FROM datasets')).mappings().all()
            media=c.execute(text('SELECT * FROM canvas_board_media')).mappings().all()
            legacy=str(CreateTable(Dataset.__table__).compile(dialect=c.dialect))
            legacy='\n'.join(line for line in legacy.splitlines() if 'board_id' not in line).replace('project_id INTEGER,','project_id INTEGER NOT NULL,')
            # The removed board FK was the last clause, leaving a trailing comma.
            import re
            legacy=re.sub(r',\s*\)$','\n)',legacy)
            c.exec_driver_sql('DROP TABLE canvas_board_media');c.exec_driver_sql('DROP TABLE datasets');c.exec_driver_sql(legacy)
            BoardMediaLink.__table__.create(c)
            for record in records:
                values={k:v for k,v in record.items() if k!='board_id'}
                c.execute(text(f'INSERT INTO datasets ({",".join(values)}) VALUES ({",".join(":"+k for k in values)})'),values)
            for record in media:c.execute(BoardMediaLink.__table__.insert(),dict(record))
            c.exec_driver_sql('CREATE INDEX ix_datasets_queue ON datasets(status,started_at)')
            c.exec_driver_sql("UPDATE sqlite_sequence SET seq=999 WHERE name='datasets'")
            c.execute(text('DELETE FROM schema_migrations WHERE version>=21'))
        upgrade=migrations.MIGRATIONS[21]
        def interrupted(c,t):upgrade(c,t);raise RuntimeError('scope migration interrupted')
        with patch.object(database,'engine',self.engine),patch.dict(migrations.MIGRATIONS,{21:interrupted}):
            with self.assertRaisesRegex(RuntimeError,'scope migration interrupted'):database.migrate()
        with self.engine.connect() as c:
            self.assertNotIn('board_id',{r[1] for r in c.exec_driver_sql('PRAGMA table_info(datasets)')})
            self.assertEqual(c.scalar(text('SELECT count(*) FROM canvas_board_media')),len(media))
            self.assertEqual(c.scalar(text('SELECT max(version) FROM schema_migrations')),20)
        with patch.object(database,'engine',self.engine):database.migrate();database.migrate()
        with self.engine.connect() as c:
            self.assertEqual(c.scalar(text('SELECT max(version) FROM schema_migrations')),23)
            self.assertEqual(c.scalar(text('SELECT count(*) FROM canvas_board_media')),len(media))
            self.assertEqual(c.scalar(text('SELECT seq FROM sqlite_sequence WHERE name=\'datasets\'')),999)
            self.assertEqual(c.exec_driver_sql('PRAGMA foreign_key_check').all(),[])
            self.assertEqual(c.scalar(text('PRAGMA integrity_check')),'ok')
        await self.preview(self.ref(row))
        self.bid=(await self.board())['id'];self.base=f'/boards/{self.bid}/resource-library'
        new=await self.upload('new.csv',b'category,revenue\nB,20\n');self.assertGreater(new['source_id'],999)
