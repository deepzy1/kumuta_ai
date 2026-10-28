"""Saved report consistency, authorization, persistence and complete safe exports."""
import json
import unittest
import test_api as fixture
import test_workspaces as workspace_fixture
import test_datasets as dataset_fixture
from app.database import SessionLocal
from app.dataset_models import Dataset
from app.document_models import StoredFile
from app import documents

class ReportTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixture.APITests.asyncSetUp
    asyncTearDown=fixture.APITests.asyncTearDown
    call=fixture.APITests.call
    ok=workspace_fixture.WorkspaceAPITests.ok
    project=workspace_fixture.WorkspaceAPITests.project
    upload=dataset_fixture.DatasetTests.upload
    def widget(self,row,key='revenue',**spec):return {'key':key,'title':'Revenue','dataset_id':row['id'],'spec':spec or {'metrics':[{'op':'sum','column':'revenue','alias':'Revenue'}]}}
    async def test_create_edit_reorder_reopen_refresh_and_zero_ai(self):
        p,_=await self.project();row=await self.upload(p['id']);base=f'/projects/{p["id"]}/data/reports'
        original={'name':'Sales report','widgets':[self.widget(row)]}
        report=await self.ok('POST',base,status=201,json=original)
        output=await self.ok('POST',base+f'/{report["id"]}/run');self.assertEqual(output['widgets'][0]['result']['rows'],[['35']])
        report=await self.ok('PUT',base+f'/{report["id"]}',json={'name':'Edited report','widgets':[self.widget(row,'count',metrics=[{'op':'count','alias':'Orders'}]),*report['widgets']],'revision':report['revision']})
        reopened=await self.ok('GET',base+f'/{report["id"]}');self.assertEqual([w['key'] for w in reopened['widgets']],['count','revenue'])
        await self.ok('PUT',base+f'/{report["id"]}',status=409,json={**original,'revision':1})
        self.assertEqual((await self.ok('GET',f'/projects/{p["id"]}/data/overview'))['reports'],1)
        await self.ok('DELETE',base+f'/{report["id"]}',json={'revision':report['revision'],'confirmation':'DELETE'})
        self.assertEqual((await self.ok('GET',base))['items'],[]);self.assertEqual(fixture.FakeClient.calls,[])
    async def test_complete_exports_formula_neutralization_and_headers(self):
        p,_=await self.project();source=b'name,revenue\n'+b'\n'.join(f'{name},{i}'.encode() for i,name in enumerate(['=1+1','+cmd','-cmd','@cmd','  =formula','normal']))
        row=await self.upload(p['id'],data=source);base=f'/projects/{p["id"]}/data/reports'
        widget=self.widget(row,operation='rows',columns=['name','revenue'],limit=2,chart='table')
        report=await self.ok('POST',base,status=201,json={'name':'=report','widgets':[widget]})
        output=await self.ok('POST',base+f'/{report["id"]}/run');self.assertEqual(len(output['widgets'][0]['result']['rows']),2)
        response=await self.call('GET',base+f'/{report["id"]}/export');self.assertEqual(response.status_code,200)
        for value in ["'=1+1","'+cmd","'-cmd","'@cmd","'  =formula","'=report"]:self.assertIn(value,response.text)
        self.assertIn('normal,5',response.text);self.assertEqual(response.headers['x-content-type-options'],'nosniff');self.assertIn('no-store',response.headers['cache-control'])
        exported=(await self.call('GET',base+f'/{report["id"]}/export?format=json')).json();self.assertEqual(len(exported['widgets'][0]['result']['rows']),6)
        self.assertEqual(fixture.FakeClient.calls,[])
    async def test_dataset_deletion_and_source_corruption_never_return_stale_results(self):
        p,_=await self.project();row=await self.upload(p['id']);base=f'/projects/{p["id"]}/data'
        report=await self.ok('POST',base+'/reports',status=201,json={'name':'Report','widgets':[self.widget(row)]})
        with SessionLocal() as db:key=db.get(StoredFile,db.get(Dataset,row['id']).file_id).storage_key
        source=documents.storage_path(key);source.write_bytes(b'corrupt')
        await self.ok('POST',base+f'/reports/{report["id"]}/run',status=409)
        await self.ok('DELETE',base+f'/datasets/{row["id"]}',json={'revision':row['revision'],'confirmation':'DELETE'})
        await self.ok('POST',base+f'/reports/{report["id"]}/run',status=409)
        await self.ok('GET',base+f'/reports/{report["id"]}/export',status=409)
        kept=await self.ok('GET',base+f'/reports/{report["id"]}');self.assertEqual(kept['widgets'][0]['dataset_id'],row['id'])
        await self.ok('PUT',base+f'/reports/{report["id"]}',json={'name':'Cleaned report','widgets':[],'revision':kept['revision']})
        self.assertEqual(fixture.FakeClient.calls,[])
    async def test_cross_owner_project_references_and_declarative_only(self):
        p,_=await self.project();q,_=await self.project();row=await self.upload(p['id']);base=f'/projects/{p["id"]}/data/reports'
        await self.ok('POST',f'/projects/{q["id"]}/data/reports',status=404,json={'name':'Invalid','widgets':[self.widget(row)]})
        await self.ok('POST',base,status=422,json={'name':'Invalid','widgets':[self.widget(row,code='print(1)')]})
        report=await self.ok('POST',base,status=201,json={'name':'Private','widgets':[self.widget(row)]})
        signup=await self.client.post('/auth/signup',json={'email':__import__('uuid').uuid4().hex+'@example.com','password':'password123'});self.headers={'Authorization':'Bearer '+signup.json()['token']}
        for suffix in ['',f'/{report["id"]}',f'/{report["id"]}/export']:await self.ok('GET',base+suffix,status=404)
        await self.ok('POST',base+f'/{report["id"]}/run',status=404)
        await self.ok('PUT',base+f'/{report["id"]}',status=404,json={'name':'Other','widgets':[],'revision':1})
        self.assertEqual(fixture.FakeClient.calls,[])
