"""D7-8.1: ordinary message persistence over shared validated services."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from sqlalchemy import select, text
import test_canvas_generation as generation
from test_canvas_resources import pdf, docx, xlsx
from app import main, documents, datasets, shared_ai, data_ai
from app.database import Conversation, Message, Usage
from app.dataset_models import Dataset

PROGRAM='root=Stack("Learning",[Calculator("Try","sum",[{"label":"Value","value":3}]),Checklist("Steps",[{"text":"Read"}])]);'


class SharedParserTests(unittest.TestCase):
    def test_mixed_markdown_lang_legacy_and_unsafe_fallback(self):
        content,spec,intro,error=shared_ai.extract('Before\n```openui\n'+PROGRAM+'\n```\nAfter')
        self.assertEqual(spec['blocks'][0]['type'],'calculator');self.assertEqual(intro,'Before\n\nAfter');self.assertIsNone(error)
        self.assertNotIn('root=Stack',content)
        old=shared_ai.extract('Legacy\n```quickui\n'+json.dumps(spec)+'\n```')
        self.assertEqual(old[1],spec)
        bad=shared_ai.extract('```openui\nroot=Unsafe("execute");\n```')
        self.assertIsNone(bad[1]);self.assertIn('could not be validated',bad[0])
        self.assertEqual(shared_ai.extract('Ordinary Markdown')[0],'Ordinary Markdown')


class SharedChatTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=generation.GenerationAPITests.asyncSetUp
    asyncTearDown=generation.GenerationAPITests.asyncTearDown
    ok=generation.GenerationAPITests.ok
    board=generation.GenerationAPITests.board

    async def setup_chat(self):
        patch.object(main,'SessionLocal',self.sessions).start()
        patch.object(documents,'SessionLocal',self.sessions).start()
        patch.object(datasets,'SessionLocal',self.sessions).start()
        patch.object(data_ai,'SessionLocal',self.sessions).start()
        patch.object(documents,'STORAGE',Path(self.temp.name)/'sources').start()
        self.cid=(await self.ok('POST','/conversations',json={}))['id']

    async def upload(self,name,raw):
        url=f'/conversations/{self.cid}/datasets' if name.endswith(('.csv','.xlsx')) else '/documents'
        data={} if url!='/documents' else {'conversation_id':str(self.cid)}
        row=await self.ok('POST',url,201,data=data,files={'file':(name,raw,'application/octet-stream')})
        while documents.process_next():pass
        while datasets.process_next():pass
        return await self.ok('GET',f'{url}/{row["id"]}')

    async def send(self,**data):
        response=await self.client.post(f'/conversations/{self.cid}/messages',headers=self.headers,data={'text':'Explain the evidence',**data})
        self.assertEqual(response.status_code,200,response.text)
        self.assertIn('event: done',response.text)
        return (await self.ok('GET',f'/conversations/{self.cid}'))['messages'][-1]

    async def test_openui_inline_state_reload_cas_and_legacy(self):
        await self.setup_chat();self.response='Before\n```openui\n'+PROGRAM+'\n```\nAfter'
        saved=await self.send();self.assertEqual(saved['quickui']['title'],'Learning');self.assertEqual(self.calls,1)
        path=f'/conversations/{self.cid}/messages/{saved["id"]}/quickui-state'
        await self.ok('PUT',path,json={'revision':0,'state':{'0':[7],'1':[True]}})
        await self.ok('PUT',path,409,json={'revision':0,'state':{}})
        await self.ok('PUT',path,422,json={'revision':1,'state':{'0':[999999]}})
        reloaded=(await self.ok('GET',f'/conversations/{self.cid}'))['messages'][-1]
        self.assertEqual(reloaded['quickui_state'],{'0':[7],'1':[True]});self.assertEqual(self.calls,1)
        self.response='```quickui\n'+json.dumps(saved['quickui'])+'\n```'
        self.assertIsNotNone((await self.send())['quickui']);self.assertEqual(self.calls,2)

    async def test_documents_all_formats_dedup_cited_scope_and_no_upload_provider(self):
        await self.setup_chat()
        rows=[]
        for name,raw in [('paper.pdf',pdf()),('outline.docx',docx()),('notes.txt',b'SQLite private evidence.'),('guide.md',b'# SQLite\nPrivate search evidence.')]:
            row=await self.upload(name,raw);self.assertEqual(row['status'],'ready');rows.append(row)
        same=await self.upload('again.txt',b'SQLite private evidence.');self.assertEqual(same['id'],rows[2]['id']);self.assertEqual(self.calls,0)
        with self.sessions() as db:
            from app.document_models import DocumentChunk
            chunk=db.scalar(select(DocumentChunk).where(DocumentChunk.document_id==rows[2]['id']))
            marker=f'D{rows[2]["id"]}:C{chunk.id}'
        self.response='SQLite evidence ['+marker+'].'
        saved=await self.send(text='SQLite',document_ids=json.dumps([rows[2]['id']]))
        self.assertEqual(saved['document_sources'][0]['citation'],marker)
        history=(await self.ok('GET',f'/conversations/{self.cid}'))['messages']
        self.assertEqual(history[-2]['document_request']['sources'][0]['filename'],'notes.txt')
        other=(await self.ok('POST','/conversations',json={}))['id']
        await self.ok('POST',f'/conversations/{other}/messages',404,data={'text':'SQLite','document_ids':json.dumps([rows[2]['id']])})
        self.assertEqual(self.calls,1)

    async def test_csv_xlsx_manual_comparison_uses_only_computed_widget_values(self):
        await self.setup_chat();rows=[]
        for name,raw in [('sales.csv',b'category,revenue\nA,10\nA,20\nB,30\n'),('book.xlsx',xlsx())]:
            row=await self.upload(name,raw);self.assertEqual(row['status'],'ready');rows.append(row)
        self.assertEqual(self.calls,0)
        item={'dataset_id':rows[0]['id'],'sha256':rows[0]['sha256'],'sheet':rows[0]['sheets'][0]['name'],
              'spec':{'metrics':[{'op':'sum','column':'revenue','alias':'Total'}],'chart':'table'}}
        computed=await self.ok('POST',f'/conversations/{self.cid}/datasets/{rows[0]["id"]}/analyze',json=item['spec'])
        self.assertEqual(computed['rows'],[['60']]);self.assertEqual(self.calls,0)
        self.response='Explanation of verified values.\n```openui\n'+PROGRAM+'\n```'
        saved=await self.send(dataset_requests=json.dumps([item]));self.assertEqual(self.calls,1)
        self.assertEqual(saved['quickui']['blocks'][0]['rows'],[['60']]);self.assertNotIn('Calculation:',saved['content']);self.assertNotIn('root=Stack',saved['content'])
        other=(await self.ok('POST','/conversations',json={}))['id']
        await self.ok('GET',f'/conversations/{other}/datasets/{rows[0]["id"]}',404)
        bad={**item,'sha256':'0'*64}
        await self.ok('POST',f'/conversations/{self.cid}/messages',409,data={'text':'sum','dataset_requests':json.dumps([bad])})
        self.assertEqual(self.calls,1)

    async def test_board_sources_never_enter_ordinary_conversation_dataset_scope(self):
        await self.setup_chat()
        cid=(await self.ok('POST',f'/boards/{self.bid}/conversations/new',201))['conversation_id']
        await self.ok('POST',f'/conversations/{cid}/datasets',422,files={'file':('private.csv',b'x\n1\n','text/csv')})
        await self.ok('POST',f'/conversations/{self.cid}/messages',415,files={'attachments':('image.webp',b'RIFFfakeWEBP','image/webp')})
        self.assertEqual(self.calls,0)

    async def test_attachment_only_send_keeps_authorized_source_labels(self):
        await self.setup_chat();row=await self.upload('guide.txt',b'SQLite private guide.')
        self.response='Ask a specific question about this guide.'
        await self.send(text='',document_ids=json.dumps([row['id']]))
        history=(await self.ok('GET',f'/conversations/{self.cid}'))['messages']
        self.assertEqual(history[-2]['document_request']['sources'][0]['filename'],'guide.txt')
        self.assertEqual(self.calls,1)

    async def test_migration_head_and_private_dataset_cascade(self):
        await self.setup_chat();row=await self.upload('sales.csv',b'name,value\nA,4\n')
        with self.sessions() as db:
            self.assertEqual(db.scalar(text('SELECT max(version) FROM schema_migrations')),23)
            db.delete(db.get(Conversation,self.cid));db.commit()
            self.assertIsNone(db.get(Dataset,row['id']))
            self.assertEqual(db.scalar(text('PRAGMA integrity_check')),'ok');self.assertEqual(db.execute(text('PRAGMA foreign_key_check')).all(),[])

    async def test_natural_language_intent_accounted_once_and_regenerate_reuses_spec(self):
        await self.setup_chat();row=await self.upload('sales.csv',b'category,revenue\nA,10\nB,20\n')
        fake_class=type(self.fake.side_effect('test'));original=fake_class.generate_content
        owner=self
        async def generate(client,**kwargs):
            previous=owner.response
            if kwargs['config'].system_instruction.startswith('Interpret a dataset question'):
                payload=json.loads(kwargs['contents'][0].parts[0].text)
                owner.assertNotIn('rows',payload);owner.assertNotIn('values',payload)
                owner.response=json.dumps({'sheet':payload['sheet'],'metrics':[{'op':'sum','column':'revenue','alias':'Total'}],'chart':'table'})
            try:return await original(client,**kwargs)
            finally:owner.response=previous
        patch.object(fake_class,'generate_content',generate).start()
        item={'dataset_id':row['id'],'sha256':row['sha256'],'sheet':row['sheets'][0]['name']}
        self.response='Verified results explained.'
        saved=await self.send(text='Sum revenue',dataset_requests=json.dumps([item]));self.assertEqual(self.calls,2)
        self.assertEqual(saved['quickui']['blocks'][0]['rows'],[['30']])
        r=await self.client.post(f'/conversations/{self.cid}/regenerate',headers=self.headers)
        self.assertEqual(r.status_code,200,r.text);self.assertEqual(self.calls,3)
        with self.sessions() as db:
            usage=list(db.scalars(select(Usage).where(Usage.conversation_id==self.cid)))
            self.assertEqual([u.kind for u in usage],['data_intent','chat','regenerate'])

    async def test_populated_v22_upgrade_failure_rollback_retry_and_preservation(self):
        await self.setup_chat()
        from sqlalchemy.schema import CreateTable
        from app import database,migrations
        from app.board_models import BoardMediaLink
        from app.dataset_models import Dataset
        import re
        board_source=await self.ok('POST',f'/boards/{self.bid}/resource-library/upload',201,files={'file':('keep.csv',b'category,revenue\nA,15\n','text/csv')})
        while datasets.process_next():pass
        self.response='```openui\n'+PROGRAM+'\n```';saved=await self.send()
        with self.engine.begin() as db:
            records=db.execute(text('SELECT * FROM datasets')).mappings().all();media=db.execute(text('SELECT * FROM canvas_board_media')).mappings().all()
            old=str(CreateTable(Dataset.__table__).compile(dialect=db.dialect))
            old='\n'.join(line for line in old.splitlines() if 'conversation_id' not in line)
            # Replace the three-scope check removed above with v22's exact boundary.
            old=re.sub(r',\s*\)$','\n)',old)
            db.exec_driver_sql('DROP TABLE canvas_board_media');db.exec_driver_sql('DROP TABLE datasets');db.exec_driver_sql(old);BoardMediaLink.__table__.create(db)
            for record in records:
                values={k:v for k,v in record.items() if k!='conversation_id'}
                db.execute(text(f'INSERT INTO datasets ({",".join(values)}) VALUES ({",".join(":"+k for k in values)})'),values)
            for record in media:db.execute(BoardMediaLink.__table__.insert(),dict(record))
            db.exec_driver_sql('CREATE INDEX ix_datasets_queue ON datasets(status,started_at)')
            db.exec_driver_sql("UPDATE sqlite_sequence SET seq=900 WHERE name='datasets'")
            db.exec_driver_sql('ALTER TABLE quickui_responses DROP COLUMN interaction_state');db.exec_driver_sql('ALTER TABLE quickui_responses DROP COLUMN state_revision')
            db.exec_driver_sql('DELETE FROM schema_migrations WHERE version=23')
        def interrupted(db,stamp):migrations.shared_chat_capabilities(db,stamp);raise RuntimeError('interrupted D781')
        with patch.object(database,'engine',self.engine),patch.dict(migrations.MIGRATIONS,{23:interrupted}):
            with self.assertRaisesRegex(RuntimeError,'interrupted D781'):database.migrate()
        with self.engine.connect() as db:
            self.assertEqual(db.scalar(text('SELECT max(version) FROM schema_migrations')),22)
            self.assertNotIn('conversation_id',{r[1] for r in db.exec_driver_sql('PRAGMA table_info(datasets)')})
        with patch.object(database,'engine',self.engine):database.migrate();database.migrate()
        with self.engine.connect() as db:
            self.assertEqual(db.scalar(text('SELECT max(version) FROM schema_migrations')),23)
            self.assertEqual(db.scalar(text('SELECT seq FROM sqlite_sequence WHERE name=\'datasets\'')),900)
            self.assertEqual(db.scalar(text('SELECT count(*) FROM canvas_board_media')),len(media))
            self.assertEqual(db.scalar(text('PRAGMA integrity_check')),'ok');self.assertEqual(db.exec_driver_sql('PRAGMA foreign_key_check').all(),[])
        reloaded=(await self.ok('GET',f'/conversations/{self.cid}'))['messages'][-1]
        self.assertEqual(reloaded['quickui'],saved['quickui']);self.assertEqual(reloaded['quickui_state'],{})
        self.assertTrue(all(p.stat().st_mode&0o777==0o600 for p in Path(self.temp.name).glob('*.bak')))
