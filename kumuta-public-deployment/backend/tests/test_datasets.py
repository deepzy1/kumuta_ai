"""Phase 3A contracts, disposable sources/SQLite, zero live AI."""
import io
import unittest
from unittest.mock import patch
import zipfile
import test_api as fixture
import test_workspaces as workspace_fixture
from app import datasets, documents
from app.dataset_parse import parse, ParseError
from app.database import SessionLocal
from app.dataset_models import Dataset
from app.document_models import StoredFile


def xlsx(sheets=None, extra=None):
    sheets = sheets or [('Sales', [['date','category','revenue'],['2026-01-01','A','10.50'],['2026-02-01','B','20']]),('Codes',[['code','active'],['001','true']])]
    from xml.sax.saxutils import escape
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml','<Types/>')
        z.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+''.join(f'<sheet name="{escape(name)}" sheetId="{i}" r:id="r{i}"/>' for i,(name,_) in enumerate(sheets,1))+'</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels','<Relationships>'+''.join(f'<Relationship Id="r{i}" Target="worksheets/sheet{i}.xml"/>' for i in range(1,len(sheets)+1))+'</Relationships>')
        for i,(_,rows) in enumerate(sheets,1):
            z.writestr(f'xl/worksheets/sheet{i}.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+''.join(f'<row r="{r}">'+''.join(f'<c r="{chr(65+c)}{r}" t="inlineStr"><is><t>{escape(v)}</t></is></c>' for c,v in enumerate(row))+'</row>' for r,row in enumerate(rows,1))+'</sheetData></worksheet>')
        for name,data in (extra or {}).items():z.writestr(name,data)
    return output.getvalue()


class ParserTests(unittest.TestCase):
    def test_csv_bom_delimiters_quotes_and_types(self):
        s=parse(b'\xef\xbb\xbfid;name;value;active;day\n001;"hello;\nworld";10.5;true;2026-01-01\n002;other;;false;2026-01-02\n','csv')[0]
        self.assertEqual(s['rows'][0][1],'hello;\nworld')
        self.assertEqual([c['type'] for c in s['columns']],['string','string','decimal','boolean','date'])
        self.assertEqual(s['columns'][2]['missing'],1)
        self.assertEqual(s['columns'][2]['average'],'10.5')
        self.assertEqual(parse(b'zip,value,big,mixed,at\n0123,01,999999999999999999,3,2026-01-01T01:02:03Z\n0124,02,888888888888888888,word,2026-01-02T01:02:03Z','csv')[0]['columns'][2]['type'],'string')
    def test_malformed_csv_and_limits(self):
        for data in [b'a,a\n1,2',b'a,b\n1',b'a,b\n"broken,2',b'\xff',b'a\n\x00',b'a\n'+b'x'*4001]:
            with self.subTest(data=data[:20]),self.assertRaises(ParseError):parse(data,'csv')
        with patch('app.dataset_parse.MAX_ROWS',1),self.assertRaises(ParseError):parse(b'a\n1\n2','csv')
        with patch('app.dataset_parse.MAX_COLUMNS',1),self.assertRaises(ParseError):parse(b'a,b\n1,2','csv')
    def test_xlsx_sheets_and_hostile_archives(self):
        s=parse(xlsx(),'xlsx');self.assertEqual([r['name'] for r in s],['Sales','Codes'])
        self.assertEqual(s[1]['rows'][0][0],'001')
        for extra in [{'../escape.xml':'x'},{'xl/vbaProject.bin':'x'},{'xl/externalLinks/externalLink1.xml':'<x/>'},{'bomb.xml':'x'*300000}, {'xl/worksheets/_rels/sheet1.xml.rels':'<Relationships><Relationship TargetMode="External"/></Relationships>'}]:
            with self.subTest(extra=list(extra)),self.assertRaises(ParseError):parse(xlsx(extra=extra),'xlsx')
        with self.assertRaises(ParseError):parse(xlsx(extra={'bad.rels':'<!DOCTYPE x [<!ENTITY a "x">]><x>&a;</x>'}),'xlsx')
        with self.assertRaises(ParseError):parse(b'notzip','xlsx')


    def test_xlsx_cached_formulas_styles_epochs_encryption_and_entry_limits(self):
        source=xlsx([('Values',[['day','total'],['a','b']])])
        out=io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(source)) as original,zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
            for entry in original.infolist():
                data=original.read(entry.filename)
                if entry.filename=='xl/worksheets/sheet1.xml':
                    data=b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>day</t></is></c><c r="B1" t="inlineStr"><is><t>total</t></is></c></row><row r="2"><c r="A2" s="1"><v>61</v></c><c r="B2"><f>RUN_UNTRUSTED_CODE()</f><v>3</v></c></row><row r="3"><c r="A3" s="1"><v>61.5</v></c><c r="B3"><f>UNCACHED()</f></c></row></sheetData></worksheet>'
                z.writestr(entry.filename,data)
            z.writestr('xl/styles.xml','<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><cellXfs><xf numFmtId="0"/><xf numFmtId="14"/></cellXfs></styleSheet>')
        data=out.getvalue();parsed=parse(data,'xlsx')[0]
        self.assertEqual(parsed['rows'],[['1900-03-01','3'],['1900-03-01T12:00:00',None]])
        self.assertIn('2 formula cells',str(parsed['warnings']))
        with self.assertRaises(ParseError):parse(xlsx(extra={f'entry{i}.xml':'x' for i in range(301)}),'xlsx')
        encrypted=bytearray(data)
        import struct
        flag=struct.unpack_from('<H',encrypted,6)[0];struct.pack_into('<H',encrypted,6,flag|1)
        central=encrypted.index(b'PK\x01\x02');flag=struct.unpack_from('<H',encrypted,central+8)[0];struct.pack_into('<H',encrypted,central+8,flag|1)
        with self.assertRaises(ParseError):parse(bytes(encrypted),'xlsx')


class DatasetTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixture.APITests.asyncSetUp
    asyncTearDown=fixture.APITests.asyncTearDown
    call=fixture.APITests.call
    ok=workspace_fixture.WorkspaceAPITests.ok
    project=workspace_fixture.WorkspaceAPITests.project
    async def upload(self,pid,name='sales.csv',data=b'category,revenue\nA,10\nB,20\nA,5',ready=True):
        row=await self.ok('POST',f'/projects/{pid}/data/datasets',status=201,files={'file':(name,data)})
        if ready:
            while datasets.process_next():pass
            row=await self.ok('GET',f'/projects/{pid}/data/datasets/{row["id"]}')
        return row
    async def test_crud_processing_pagination_stats_private_storage_zero_ai(self):
        p,_=await self.project();base=f'/projects/{p["id"]}/data'
        row=await self.upload(p['id']);self.assertEqual(row['status'],'ready')
        duplicate=await self.upload(p['id']);self.assertEqual(duplicate['id'],row['id'])
        with SessionLocal() as db:key=db.get(StoredFile,db.get(Dataset,row['id']).file_id).storage_key
        path=documents.storage_path(key);self.assertEqual(path.stat().st_mode&0o777,0o600)
        documents.cleanup_files();self.assertTrue(path.exists())
        preview=await self.ok('GET',base+f'/datasets/{row["id"]}/preview?limit=2');self.assertTrue(preview['has_more']);self.assertEqual(len(preview['items']),2)
        schema=await self.ok('GET',base+f'/datasets/{row["id"]}/schema');self.assertEqual(schema['columns'][1]['sum'],'35')
        renamed=await self.ok('PATCH',base+f'/datasets/{row["id"]}',json={'name':'Revenue','revision':row['revision']})
        await self.ok('PATCH',base+f'/datasets/{row["id"]}',status=409,json={'name':'Stale','revision':row['revision']})
        self.assertEqual((await self.ok('GET',base+'/overview'))['rows'],3)
        await self.ok('DELETE',base+f'/datasets/{row["id"]}',json={'revision':renamed['revision'],'confirmation':'DELETE'})
        self.assertFalse(path.exists());self.assertEqual(fixture.FakeClient.calls,[])
    async def test_failure_retry_unsupported_and_oversized(self):
        p,_=await self.project();base=f'/projects/{p["id"]}/data/datasets'
        row=await self.upload(p['id'],data=b'a,a\n1,2');self.assertEqual(row['status'],'error')
        await self.ok('POST',base+f'/{row["id"]}/retry',json={'revision':row['revision']})
        while datasets.process_next():pass
        for name,data,status in [('data.xls',b'x',415),('empty.csv',b'',413),('bad.xlsx',b'notzip',422)]:
            await self.ok('POST',base,status=status,files={'file':(name,data)})
        with patch.object(datasets,'MAX_FILE',10):await self.ok('POST',base,status=413,files={'file':('big.csv',b'x'*11)})
        row=await self.upload(p['id'],data=b'a\n2',ready=False)
        with SessionLocal() as db:
            d=db.get(Dataset,row['id']);d.status='processing';d.started_at='2000-01-01';db.commit()
        datasets.process_next();self.assertEqual((await self.ok('GET',base+f'/{row["id"]}'))['status'],'error')
        self.assertEqual(fixture.FakeClient.calls,[])
    async def test_sheets_ownership_tampering_and_project_cascade(self):
        p,_=await self.project('Owner');q,_=await self.project('Other project');row=await self.upload(p['id'],'book.xlsx',xlsx());base=f'/projects/{p["id"]}/data/datasets/{row["id"]}'
        self.assertEqual((await self.ok('GET',base+'/preview?sheet=Codes'))['items'][0][0],'001')
        await self.ok('GET',base+'/preview?sheet=Absent',status=422)
        await self.ok('GET',f'/projects/{q["id"]}/data/datasets/{row["id"]}',status=404)
        with SessionLocal() as db:key=db.get(StoredFile,db.get(Dataset,row['id']).file_id).storage_key
        token=self.headers
        signup=await self.client.post('/auth/signup',json={'email':__import__('uuid').uuid4().hex+'@example.com','password':'password123'})
        self.headers={'Authorization':'Bearer '+signup.json()['token']}
        for suffix in ['', '/preview','/schema']:await self.ok('GET',base+suffix,status=404)
        await self.ok('POST',f'/projects/{p["id"]}/data/datasets',status=404,files={'file':('x.csv',b'a\n1')})
        self.headers=token
        await self.ok('DELETE',f'/projects/{p["id"]}',json={'revision':p['revision'],'confirm_name':p['name']})
        documents.cleanup_files();self.assertFalse(documents.storage_path(key).exists())
        self.assertEqual(fixture.FakeClient.calls,[])
