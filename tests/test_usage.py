"""Accounting, calendar boundaries and access controls for the monthly dashboard."""
import json
import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path
from aiohttp.test_utils import TestClient,TestServer
from app import web_app
from backups import Backups
from config import Settings
from engine import Engine
from security import Keys,secret_file
from service import Service,Incoming
from store import Store,Scope
from usage import monthly_usage,ROME


class Response:
    status=200
    def __init__(self,payload): self.payload=payload
    async def __aenter__(self): return self
    async def __aexit__(self,*args): pass
    async def json(self): return self.payload


class ModelSession:
    def __init__(self,payload): self.payload=payload; self.calls=0
    def post(self,*args,**kwargs): self.calls+=1; return Response(self.payload)


class UsageTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.settings=Settings(root=Path(self.tmp.name),admins=(1,),allowed=(2,3))
        self.store=Store(self.settings.data/'alba.sqlite3')
        self.keys=Keys(self.store,secret_file(self.settings.data/'auth.key'))
        self.backups=Backups(self.store,self.settings)
        self.model=ModelSession({'message':{'content':json.dumps({'reply':'Come ti senti?',
            'used_memory_ids':[],'personal_claims':[]})},'prompt_eval_count':100,'eval_count':23})
        self.engine=Engine(self.store,self.settings,self.model)
        self.service=Service(self.store,self.settings,self.keys,self.engine,self.backups)
        for uid,name in ((1,'Admin'),(2,'Alice'),(3,'Bob')): self.store.register(uid,name)
        self.now=datetime(2026,9,29,12,tzinfo=ROME)
        self.store.set_setting('token_tracking_since',datetime(2026,9,1,tzinfo=ROME).timestamp())

    def tearDown(self):
        self.store.close(); self.tmp.cleanup()

    def record(self,uid=2,day=5,prompt=100,output=20,scope=None,mid=None):
        self.store.record_tokens(scope or Scope('user',uid),uid,'model','ollama',prompt,output,mid,
            datetime(2026,9,day,12,tzinfo=ROME).timestamp())

    def month(self,uid=2,**kwargs): return monthly_usage(self.store,uid,'2026-09',now=self.now,**kwargs)

    async def http(self,path,uid=2):
        cookie,_=self.keys.session(self.keys.issue(uid,uid,'web'))
        client=TestClient(TestServer(web_app(self.service))); await client.start_server()
        try:
            response=await client.get(path,headers={'Cookie':'session='+cookie})
            return response.status,await response.json()
        finally: await client.close()

    def test_01_private_counts_isolated(self):
        self.record(); self.record(uid=3,prompt=900,output=800)
        result=self.month()
        self.assertEqual(result['totals']['total_tokens'],120)
        self.assertEqual(result['totals']['requests'],1)

    def test_02_admin_total_includes_groups_and_web(self):
        self.record(); self.record(uid=3,scope=Scope('group',-10),prompt=200,output=50)
        result=self.month(uid=1,all_users=True)
        self.assertEqual(result['totals']['total_tokens'],370)
        self.assertEqual(result['scope'],'bot')

    def test_03_group_other_authors_not_in_personal_usage(self):
        self.record(uid=3,scope=Scope('group',-10))
        self.assertEqual(self.month()['totals']['requests'],0)

    def test_04_tracking_start_does_not_invent_historical_zeros(self):
        self.store.set_setting('token_tracking_since',datetime(2026,9,29,11,tzinfo=ROME).timestamp())
        days=self.month()['days']
        self.assertFalse(days[27]['available']); self.assertTrue(days[28]['available'])
        self.assertTrue(days[28]['partial']); self.assertTrue(days[29]['future'])

    def test_05_calendar_leap_year(self):
        self.assertEqual(len(monthly_usage(self.store,2,'2024-02')['days']),29)
        self.assertEqual(len(monthly_usage(self.store,2,'2025-02')['days']),28)

    def test_06_invalid_months_rejected(self):
        for value in ('2026-13','2026-00','2026-1','1999-12','2101-01','../data','',None):
            with self.subTest(value=value),self.assertRaises(ValueError): monthly_usage(self.store,2,value)

    def test_07_timezone_midnight(self):
        # 22:30 UTC in summer is the following date in Rome.
        self.store.record_tokens(Scope('user',2),2,'model','ollama',5,3,
            timestamp=datetime(2026,8,31,22,30,tzinfo=timezone.utc).timestamp())
        self.assertEqual(self.month()['days'][0]['total_tokens'],8)

    def test_08_dst_day_has_correct_boundaries(self):
        self.store.set_setting('token_tracking_since',datetime(2026,10,1,tzinfo=ROME).timestamp())
        for hour in (0,1):
            self.store.record_tokens(Scope('user',2),2,'m','ollama',10,1,
                timestamp=datetime(2026,10,25,hour,30,tzinfo=timezone.utc).timestamp())
        result=monthly_usage(self.store,2,'2026-10',now=datetime(2026,10,26,tzinfo=ROME))
        self.assertEqual(result['days'][24]['requests'],2)
        self.assertEqual(result['days'][24]['total_tokens'],22)

    def test_09_missing_counts_marked_without_estimates(self):
        self.record(prompt=None,output=7)
        self.assertEqual(self.month()['totals']['total_tokens'],7)
        self.assertEqual(self.month()['totals']['unreported'],1)

    def test_10_malformed_counts_not_accepted(self):
        for value in (-1,True,'200',2.5,2**63): self.record(prompt=value,output=value)
        result=self.month()['totals']
        self.assertEqual(result['total_tokens'],0); self.assertEqual(result['unreported'],5)

    def test_11_forget_user_erases_accounting(self):
        self.record(); self.record(uid=3)
        self.store.forget_user(2)
        self.assertEqual(self.month()['totals']['requests'],0)
        self.assertEqual(self.month(uid=3)['totals']['requests'],1)

    def test_12_forget_source_erases_usage(self):
        scope=Scope('user',2)
        mid=self.store.add_message(scope,2,'user','Mi chiamo Alice')
        mem=self.store.add_memory(scope,'Mi chiamo Alice','personal',[mid])
        self.record(mid=mid)
        self.store.forget_memory(scope,mem)
        self.assertEqual(self.month()['totals']['requests'],0)

    async def test_13_regular_user_cannot_view_bot_totals(self):
        status,_=await self.http('/api/usage?scope=bot')
        self.assertEqual(status,403)

    async def test_14_regular_user_cannot_forge_owner(self):
        for query in ('user_id=3','group_id=-10','chat_id=3','scope=group'):
            with self.subTest(query=query):
                status,_=await self.http('/api/usage?'+query); self.assertEqual(status,403)

    async def test_15_authenticated_api_scopes(self):
        self.record(); self.record(uid=3,prompt=200,output=50)
        status,result=await self.http('/api/usage?month=2026-09')
        self.assertEqual(status,200); self.assertEqual(result['totals']['total_tokens'],120)
        status,result=await self.http('/api/usage?month=2026-09&scope=bot',uid=1)
        self.assertEqual(status,200); self.assertEqual(result['totals']['total_tokens'],370)

    async def test_16_api_reports_admin_role(self):
        self.assertTrue((await self.http('/api/me',uid=1))[1]['is_admin'])
        self.assertFalse((await self.http('/api/me',uid=2))[1]['is_admin'])

    async def test_17_real_backend_response_counts(self):
        await self.service.handle(Incoming(2,'Alice',2,'private','Ciao, come va?'))
        rows=self.store.rows('SELECT * FROM token_usage')
        self.assertEqual(len(rows),1)
        self.assertEqual((rows[0]['input_tokens'],rows[0]['output_tokens']),(100,23))
        self.assertEqual(rows[0]['scope'],'user:2')
        self.assertIsNone(self.engine._usage_context)

    async def test_18_invalid_model_text_still_records_consumed_tokens(self):
        self.model.payload['message']['content']='JSON NON VALIDO'
        await self.service.handle(Incoming(2,'Alice',2,'private','Ciao'))
        rows=self.store.rows('SELECT * FROM token_usage')
        self.assertEqual(rows[0]['output_tokens'],23); self.assertIsNone(self.engine._usage_context)

    async def test_19_deterministic_recall_does_not_invent_token_usage(self):
        await self.service.handle(Incoming(2,'Alice',2,'private','Ti ricordi il mio nome?'))
        self.assertEqual(self.model.calls,0); self.assertEqual(self.store.rows('SELECT * FROM token_usage'),[])

    async def test_20_llamacpp_usage_supported(self):
        self.settings.backend='llamacpp'
        self.model.payload={'choices':[{'message':{'content':json.dumps({'reply':'Come ti senti?',
            'used_memory_ids':[],'personal_claims':[]})}}],'usage':{'prompt_tokens':50,'completion_tokens':12}}
        await self.service.handle(Incoming(2,'Alice',2,'private','Ciao'))
        row=self.store.rows('SELECT * FROM token_usage')[0]
        self.assertEqual((row['input_tokens'],row['output_tokens']),(50,12))

    async def test_21_llamacpp_missing_metadata_flagged(self):
        self.settings.backend='llamacpp'
        self.model.payload={'choices':[{'message':{'content':json.dumps({'reply':'Come ti senti?',
            'used_memory_ids':[],'personal_claims':[]})}}],'usage':None}
        await self.service.handle(Incoming(2,'Alice',2,'private','Ciao'))
        row=self.store.rows('SELECT * FROM token_usage')[0]
        self.assertIsNone(row['input_tokens']); self.assertIsNone(row['output_tokens'])

    async def test_22_unauthenticated_usage_denied(self):
        client=TestClient(TestServer(web_app(self.service))); await client.start_server()
        try: self.assertEqual((await client.get('/api/usage')).status,403)
        finally: await client.close()


if __name__=='__main__': unittest.main()
