import asyncio
import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
from aiohttp.test_utils import TestClient, TestServer
from app import web_app
from backups import Backups
from config import Settings
from engine import Engine
from security import Keys, secret_file
from service import Service, Incoming
from store import Store, Scope
from core.runtime import Core

ROOT = Path(__file__).resolve().parents[1]


def output(text='Una scoperta, finalmente. **Interessante.**'):
    return dict(text=text,note='Riflessione sintetica.',summary='Ho imparato a collegare le fonti.',
                action='none',query='',whatsapp='',telegram='',emotions={'curiosità':.1},initiative=.6,volatility=.4)


class Response:
    status=200
    def __init__(self, body): self.body=body;self.content=self
    async def __aenter__(self): return self
    async def __aexit__(self,*args): pass
    async def json(self): return self.body
    def __aiter__(self):
        async def lines():
            for part in ({'message':{'content':output()['text']}}, {'done':True,'prompt_eval_count':80,'eval_count':40}):
                yield (json.dumps(part)+'\n').encode()
        return lines()


class Model:
    def __init__(self): self.calls=[]
    def post(self,url,json=None,**kwargs):
        self.calls.append((url,json))
        if url.endswith('/api/embed'):
            return Response({'embeddings':[[1.,.2,.3] for _ in json['input']],'prompt_eval_count':10})
        return Response({'message':{'content':__import__('json').dumps(output())},'prompt_eval_count':80,'eval_count':40})


class CoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        for name in ('notte.html','notte.css','notte.js','web.html','web.css','web.js'):
            shutil.copy2(ROOT/name,self.root/name)
        self.settings=Settings(root=self.root,admins=(1,),allowed=(2,))
        self.store=Store(self.settings.data/'alba.sqlite3')
        self.keys=Keys(self.store,secret_file(self.settings.data/'auth.key'))
        self.model=Model()
        self.service=Service(self.store,self.settings,self.keys,Engine(self.store,self.settings,self.model),Backups(self.store,self.settings))
        for uid in (1,2): self.store.register(uid,'Matt' if uid==1 else 'Altro')
        self.client=TestClient(TestServer(web_app(self.service)));await self.client.start_server()
        self.core=self.service.core
        self.headers={}
        for uid in (1,2):
            cookie,csrf=self.keys.create_session(uid,True)
            self.headers[uid]={'Cookie':'session='+cookie,'X-CSRF-Token':csrf}
    async def asyncTearDown(self):
        await self.client.close();self.store.close();self.tmp.cleanup()
    async def req(self,path,method='GET',data=None,uid=1):
        return await self.client.request(method,path,headers=self.headers[uid],json=data)

    async def test_admin_access_csrf_and_untrusted_config(self):
        for path in ('/api/notte/status','/api/notte/events','/api/notte/export','/api/notte/stream','/api/notte/diary','/api/notte/ssd-plan'):
            response=await self.req(path,uid=2);self.assertEqual(response.status,403)
        response=await self.client.post('/api/notte/action',json={'action':'reflection'},headers={'Cookie':self.headers[1]['Cookie']})
        self.assertEqual(response.status,403)
        response=await self.req('/api/notte/action','POST',{'action':'config','config':{'telegram_matt_id':2}})
        self.assertEqual(response.status,403)
        response=await self.req('/api/notte/status');self.assertEqual(response.status,200)

    async def test_advanced_ssd_failure_never_substitutes_smaller_model(self):
        self.core.configure({'profile':'advanced','ssd_enabled':True,'advanced_code_model':'qwen2.5-coder:14b'})
        self.core.ssd.chat=AsyncMock(side_effect=ValueError('Memoria insufficiente'))
        await self.core.work('chat','Ciao')
        self.assertIn('Memoria insufficiente',self.core.error)
        self.assertEqual(self.core.ssd.chat.call_args.args[0],'qwen2.5-coder:14b')
        self.assertFalse(any(url.endswith('/api/chat') for url,_ in self.model.calls))
        self.assertTrue(self.store.rows("SELECT * FROM core_events WHERE role='user' AND content='Ciao'"))
        self.assertFalse(self.store.rows("SELECT * FROM core_events WHERE role='assistant'"))

    async def test_emotions_survive_restart_and_clamp(self):
        self.core.update_emotions({'rabbia':200,'curiosità':-200},'test')
        rebuilt=Core(self.service)
        self.assertEqual(rebuilt.emotions,self.core.emotions)
        self.assertTrue(all(0<=v<=1 for v in rebuilt.emotions.values()))
        with self.assertRaises(ValueError): self.core.update_emotions({'rabbia':float('nan')},'test')

    async def test_consolidation_retry_and_connector_isolation(self):
        self.core.event('files','document','Una parola rara: telescopio e galassie.')
        self.core.event('notes','note','Segreto riservato interno.')
        self.core.configure({'connectors':{'notes':False}})
        await self.core.work('consolidation')
        self.assertEqual(self.core.error,'')
        vectors=self.store.rows('SELECT * FROM core_chunks')
        self.assertTrue(vectors);self.assertTrue(all(r['embedding'] for r in vectors))
        memories=await self.core.retrieve('telescopio')
        self.assertTrue(memories);self.assertTrue(all(r['category']!='notes' for r in memories))
        self.core.configure({'connectors':{k:False for k in self.core.config['connectors']}})
        self.assertEqual(await self.core.retrieve('telescopio'),[])
        self.assertEqual(self.store.rows('SELECT * FROM core_cycles')[0]['status'],'ok')

    async def test_failed_embedding_is_logged_and_retried(self):
        self.core.event('files','document','Documento da conservare.')
        self.core.embed=AsyncMock(side_effect=ValueError('Missing'))
        await self.core.work('consolidation')
        self.assertEqual(self.store.rows('SELECT status FROM core_cycles')[0]['status'],'degraded')
        self.assertIsNone(self.store.rows('SELECT embedding FROM core_chunks')[0]['embedding'])
        self.core.embed=AsyncMock(return_value=[[.3,.4]])
        await self.core.work('consolidation')
        self.assertIsNotNone(self.store.rows('SELECT embedding FROM core_chunks')[0]['embedding'])

    async def test_local_generation_and_global_tokens(self):
        await self.core.work('chat','Che cosa pensi dei telescopi?')
        self.assertEqual(self.core.error,'')
        self.assertTrue(self.store.rows("SELECT * FROM core_events WHERE role='assistant'"))
        self.assertTrue(all(url.startswith('http://127.0.0.1:11434') for url,payload in self.model.calls))
        self.store.record_tokens(Scope('user',1),1,'test','ollama',20,10)
        self.assertEqual(self.core.snapshot()['lifetime_tokens'],150)
        old=self.core.snapshot()['lifetime_tokens'];self.store.set_setting('core_stats_since',time.time()+1)
        self.assertEqual(self.core.snapshot()['lifetime_tokens'],old)
        self.assertEqual(self.core.snapshot()['tokens'],[])
        chat_call=next(payload for url,payload in self.model.calls if url.endswith('/api/chat'))
        self.assertTrue(chat_call['stream']);self.assertNotIn('format',chat_call)
        self.assertEqual(chat_call['model'],self.core.config['model'])
        self.assertEqual(chat_call['options']['num_predict'],256)

    async def test_telegram_private_pairing_target_without_daily_cap(self):
        event=Incoming(1,'Matt',1,'private','/notte')
        result=await self.service.handle(event)
        self.assertIn('associato',result.text)
        self.assertEqual(self.core.config['telegram_matt_id'],1)
        sent=AsyncMock();self.core.telegram_send=sent
        for _ in range(8): await self.core.send_telegram('Un pensiero autonomo.')
        self.assertEqual(sent.await_count,8)
        self.assertTrue(all(call.args[0]==1 for call in sent.await_args_list))
        result=await self.service.handle(Incoming(2,'Altro',2,'private','/notte'))
        self.assertIn('riservata',result.text)
        self.assertEqual(self.core.config['telegram_matt_id'],1)
        await self.service.handle(Incoming(1,'Matt',1,'private','/notte off'))
        self.assertFalse(self.core.config['telegram_enabled'])

    async def test_overload_no_inference_and_failure_backoff(self):
        self.service.performance.snapshot={'ram':{'percent':95},'cpu_percent':99,'temperature_c':80}
        await self.core.work('chat','Ciao')
        self.assertEqual(self.model.calls,[])
        self.assertTrue(self.core.error);self.assertGreater(self.core.retry_after,time.time())

    async def test_live_stream_session_revocation(self):
        ws=await self.client.ws_connect('/api/notte/stream',headers=self.headers[1])
        update=await ws.receive_json();self.assertIn('mood',update)
        self.store.execute('DELETE FROM web_sessions WHERE user_id=1')
        message=await ws.receive(timeout=4)
        self.assertIn(message.type,(8,257));await ws.close()

    async def test_encrypted_backup_contains_core_state(self):
        self.core.event('files','document','Memoria Notte da conservare.')
        path=self.service.backups.create('manual')
        target=self.root/'restore.sqlite3';self.service.backups.decrypt(path,target)
        import sqlite3
        with sqlite3.connect(target) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM core_events').fetchone()[0],1)
