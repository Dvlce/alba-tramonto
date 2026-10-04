import asyncio
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from datetime import datetime
from aiohttp.test_utils import TestClient,TestServer
from app import web_app
from backups import Backups
from config import Settings
from engine import Engine,remove_repeated_questions
from security import Keys,secret_file
from service import Service,Incoming
from store import Store,Scope
from maintenance_tasks import memory_cycle
from usage import ROME
from telegram_bot import Telegram


class WaitingEngine(Engine):
    async def generate(self,messages):
        self.started.set()
        await self.release.wait()
        return {'reply':'Possiamo affrontare una cosa alla volta.','used_memory_ids':[],'personal_claims':[]}


class ControlsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.settings=Settings(root=Path(self.tmp.name),admins=(1,),allowed=(2,3))
        self.store=Store(self.settings.data/'alba.sqlite3'); self.keys=Keys(self.store,secret_file(self.settings.data/'auth.key'))
        self.backups=Backups(self.store,self.settings); self.engine=WaitingEngine(self.store,self.settings,None)
        self.engine.started=asyncio.Event(); self.engine.release=asyncio.Event()
        self.service=Service(self.store,self.settings,self.keys,self.engine,self.backups)
        for uid,name in ((1,'Admin'),(2,'Alice'),(3,'Bob')): self.store.register(uid,name)

    def tearDown(self): self.store.close(); self.tmp.cleanup()
    def event(self,text,uid=2,kind='private',chat=None,transport='telegram'):
        return Incoming(uid,self.store.user_name(uid),chat or uid,kind,text,mention_bot=True,transport=transport)

    async def request(self,path,body=None,uid=1,csrf=True):
        cookie,token=self.keys.session(self.keys.issue(uid,uid,'web'))
        client=TestClient(TestServer(web_app(self.service))); await client.start_server()
        headers={'Cookie':'session='+cookie}
        if csrf: headers['X-CSRF-Token']=token
        try:
            response=await (client.post(path,json=body,headers=headers) if body is not None else client.get(path,headers=headers))
            return response.status,await response.json()
        finally: await client.close()

    async def test_01_password_reusable_and_owner_bound(self):
        name,password=self.keys.set_web_password(2,2)
        for _ in range(2):
            cookie,_=await self.keys.password_session(name,password)
            self.assertEqual(self.keys.identify(cookie)['user_id'],2)

    async def test_02_password_wrong_and_unknown_rejected(self):
        name,password=self.keys.set_web_password(2,2)
        for user,pw in ((name,'wrong'),('unknown',password)):
            with self.assertRaises(PermissionError): await self.keys.password_session(user,pw)

    async def test_03_password_not_stored_in_plaintext_or_audit(self):
        name,password=self.keys.set_web_password(2,2)
        self.assertNotIn(password,str(self.store.rows('SELECT * FROM web_credentials')))
        self.assertNotIn(password,str(self.store.rows('SELECT * FROM audit_logs')))

    async def test_04_password_rotation_revokes_old_sessions(self):
        name,old=self.keys.set_web_password(2,2); cookie,_=await self.keys.password_session(name,old)
        name,new=self.keys.set_web_password(2,2)
        with self.assertRaises(PermissionError): self.keys.identify(cookie)
        with self.assertRaises(PermissionError): await self.keys.password_session(name,old)
        await self.keys.password_session(name,new)

    async def test_05_password_revocation_and_forget(self):
        name,password=self.keys.set_web_password(2,2); self.keys.revoke_web_password(2,2)
        with self.assertRaises(PermissionError): await self.keys.password_session(name,password)
        self.keys.set_web_password(2,2); self.store.forget_user(2)
        self.assertEqual(self.store.rows('SELECT * FROM web_credentials'),[])

    def test_06_user_cannot_reset_someone_elses_password(self):
        with self.assertRaises(PermissionError): self.keys.set_web_password(2,3)

    async def test_07_password_creation_private_telegram_only(self):
        for event in (self.event('/web_password',kind='group',chat=-10),self.event('/web_password',transport='web')):
            result=await self.service.handle(event); self.assertNotIn('Password:',result.text)

    async def test_08_auto_access_binds_key_to_sender(self):
        self.store.set_setting('automatic_web_access',1)
        result=await self.service.handle(self.event('/web_key',uid=99))
        self.assertTrue(self.store.allowed(99))
        key=result.text.splitlines()[1]; cookie,_=self.keys.session(key)
        self.assertEqual(self.keys.identify(cookie)['user_id'],99)

    async def test_09_auto_access_private_only_and_optional(self):
        self.store.set_setting('automatic_web_access',1)
        await self.service.handle(self.event('/web_key',uid=99,kind='group',chat=-10))
        self.assertFalse(self.store.allowed(99))
        self.store.set_setting('automatic_web_access',0)
        await self.service.handle(self.event('/web_key',uid=99)); self.assertFalse(self.store.allowed(99))

    async def test_10_auto_access_limit_twenty(self):
        for uid in range(4,21): self.store.authorize(uid,20)
        self.store.set_setting('automatic_web_access',1)
        result=await self.service.handle(self.event('/web_key',uid=99))
        self.assertFalse(self.store.allowed(99)); self.assertIn('Limite',result.text)

    async def test_11_admin_panel_and_actions_forbidden_to_users(self):
        for path,body in (('/api/admin',None),('/api/admin/users',{'action':'allow','user_id':'99'}),
                          ('/api/admin/action',{'action':'pause'}),('/api/admin/memories?user_id=3',None)):
            status,_=await self.request(path,body,uid=2); self.assertEqual(status,403)

    async def test_12_admin_allow_by_pasted_id_and_revoke(self):
        status,_=await self.request('/api/admin/users',{'action':'allow','user_id':' 99 '})
        self.assertEqual(status,200); self.assertTrue(self.store.allowed(99))
        status,_=await self.request('/api/admin/users',{'action':'deny','user_id':'99'})
        self.assertEqual(status,200); self.assertFalse(self.store.allowed(99))

    async def test_13_admin_cannot_disable_self_and_invalid_ids(self):
        for value in ('1','-10','not-id',str(2**63),True):
            status,_=await self.request('/api/admin/users',{'action':'deny','user_id':value})
            self.assertEqual(status,400)
        self.assertTrue(self.store.allowed(1))

    async def test_14_admin_writes_require_csrf(self):
        status,_=await self.request('/api/admin/users',{'action':'allow','user_id':'99'},csrf=False)
        self.assertEqual(status,403); self.assertFalse(self.store.allowed(99))

    async def test_15_pause_resume_and_auto_access_controls(self):
        await self.request('/api/admin/action',{'action':'pause'})
        result=await self.service.handle(self.event('Ciao'))
        self.assertIn('pausa',result.text); self.assertFalse(self.engine.started.is_set())
        await self.request('/api/admin/action',{'action':'resume'})
        await self.request('/api/admin/action',{'action':'automatic_access','enabled':True})
        self.assertEqual(self.store.setting('bot_paused'),'0')
        self.assertEqual(self.store.setting('automatic_web_access'),'1')

    async def test_16_group_control_requires_telegram_group_admin(self):
        self.store.execute('INSERT INTO groups VALUES(-10,0,0,0)')
        async def no(*args): return False
        self.service.group_admin_check=no
        status,_=await self.request('/api/admin/groups',{'group_id':'-10','field':'enabled','enabled':True})
        self.assertEqual(status,400)
        async def yes(*args): return True
        self.service.group_admin_check=yes
        status,_=await self.request('/api/admin/groups',{'group_id':'-10','field':'enabled','enabled':True})
        self.assertEqual(status,200)

    async def test_17_stop_interrupts_generation_and_releases_lock(self):
        task=asyncio.create_task(self.service.handle(self.event('Mi chiamo Alice')))
        await self.engine.started.wait()
        result=await self.service.handle(self.event('/stop'))
        self.assertIn('interrotta',result.text)
        result=await task; self.assertTrue(result.cancelled)
        self.assertFalse(self.engine.lock.locked()); self.assertEqual(self.engine.waiting,0)
        self.assertEqual(self.store.profile(2)[0]['content'],'Mi chiamo Alice')
        self.assertEqual(self.store.rows('SELECT * FROM token_usage')[0]['input_tokens'],None)

    async def test_18_stop_cannot_interrupt_other_user(self):
        task=asyncio.create_task(self.service.handle(self.event('Ciao'))); await self.engine.started.wait()
        result=await self.service.handle(self.event('/stop',uid=3))
        self.assertIn('Non c’è',result.text); self.assertFalse(task.done())
        await self.service.handle(self.event('/stop')); await task

    async def test_19_web_cancel_owner_csrf_and_retry(self):
        client=TestClient(TestServer(web_app(self.service))); await client.start_server()
        alice,csrf=self.keys.session(self.keys.issue(2,2,'web')); bob,bcsrf=self.keys.session(self.keys.issue(3,3,'web'))
        headers={'Cookie':'session='+alice,'X-CSRF-Token':csrf}
        try:
            response=await client.post('/api/chat',json={'message':'Ciao'},headers=headers); jid=(await response.json())['job_id']
            await self.engine.started.wait()
            path='/api/jobs/'+jid+'/cancel'
            self.assertEqual((await client.post(path,json={},headers={'Cookie':'session='+bob,'X-CSRF-Token':bcsrf})).status,403)
            self.assertEqual((await client.post(path,json={},headers={'Cookie':'session='+alice})).status,403)
            self.assertEqual((await client.post(path,json={},headers=headers)).status,200)
            response=await client.get('/api/jobs/'+jid,headers=headers); self.assertTrue((await response.json())['cancelled'])
            self.engine.release.set()
            response=await client.post('/api/chat',json={'message':'Nuova conversazione'},headers=headers)
            self.assertEqual(response.status,202)
        finally: await client.close()

    def test_20_repeated_question_removed_without_discarding_advice(self):
        old=[{'role':'assistant','content':'Qual è la parte che ti preoccupa di più?'}]
        result=remove_repeated_questions('Parti dal compito più piccolo e dedica dieci minuti. Qual è la parte che ti preoccupa di più?',old)
        self.assertNotIn('?',result); self.assertIn('dieci minuti',result)

    def test_21_different_question_is_preserved(self):
        reply='Quale passo vuoi provare oggi?'
        self.assertEqual(remove_repeated_questions(reply,[{'role':'assistant','content':'Come ti senti?'}]),reply)

    async def test_22_memory_flush_sources_and_namespace_isolation(self):
        for scope,uid,text in ((Scope('user',2),2,'Mi chiamo PRIVATO_ALICE'),(Scope('group',-10),3,'Mi chiamo PUBBLICO_BOB')):
            self.store.add_message(scope,uid,'user',text)
        await memory_cycle(self.store)
        self.assertEqual(self.store.profile(2)[0]['content'],'Mi chiamo PRIVATO_ALICE')
        groups=self.store.memories(Scope('group',-10))
        self.assertEqual(groups[0]['content'],'Mi chiamo PUBBLICO_BOB')
        self.assertNotIn('PRIVATO_ALICE',str(groups))
        self.assertEqual(len(self.store.rows("SELECT * FROM summaries WHERE summary_kind='conversation'")),2)

    async def test_23_flush_is_idempotent_and_erasure_not_resurrected(self):
        self.store.add_message(Scope('user',2),2,'user','Mi chiamo Alice')
        await memory_cycle(self.store); await memory_cycle(self.store)
        self.assertEqual(len(self.store.profile(2)),1)
        self.store.forget_user(2); await memory_cycle(self.store)
        self.assertEqual(self.store.profile(2),[])

    async def test_24_night_does_not_promote_inferences(self):
        mid=self.store.add_message(Scope('user',2),2,'user','Una possibile interpretazione')
        self.store.add_memory(Scope('user',2),'Forse interesse','personal',[mid],evidence='inference')
        await memory_cycle(self.store,night=True,now=datetime(2026,9,29,23,tzinfo=ROME))
        self.assertEqual(self.store.profile(2),[]); self.assertEqual(self.store.setting('memory_night_last'),'2026-09-29')

    async def test_25_admin_memories_are_scoped_and_audited(self):
        for uid,name in ((2,'Alice'),(3,'Bob')):
            mid=self.store.add_message(Scope('user',uid),uid,'user','Mi chiamo '+name)
            self.store.add_memory(Scope('user',uid),'Mi chiamo '+name,'personal',[mid])
        key=self.keys.issue(2,2,'memory_read');await self.request('/api/admin/memory-access',{'user_id':'2','token':key})
        status,result=await self.request('/api/admin/memories?user_id=2')
        self.assertEqual(status,200); self.assertNotIn('Bob',json.dumps(result))
        self.assertTrue(self.store.rows("SELECT * FROM audit_logs WHERE action='web_memory_inspect'"))

    async def test_26_auto_access_does_not_override_admin_revocation(self):
        self.store.set_setting('automatic_web_access',1)
        await self.request('/api/admin/users',{'action':'deny','user_id':'2'})
        await self.service.handle(self.event('/web_key'))
        self.assertFalse(self.store.allowed(2))
        await self.request('/api/admin/users',{'action':'allow','user_id':'2'})
        self.assertTrue(self.store.allowed(2))

    async def test_27_password_rotation_during_login_rejects_old_hash(self):
        name,old=self.keys.set_web_password(2,2)
        started=asyncio.Event(); release=asyncio.Event()
        async def delayed_hash(function,*args):
            started.set(); await release.wait()
            return function(*args)
        with patch('security.asyncio.to_thread',delayed_hash):
            pending=asyncio.create_task(self.keys.password_session(name,old))
            await started.wait()
            self.keys.set_web_password(2,2)
            release.set()
            with self.assertRaises(PermissionError): await pending
        self.assertEqual(self.store.rows('SELECT * FROM web_sessions WHERE user_id=2'),[])

    async def test_31_telegram_optional_updates_do_not_stop_the_bot(self):
        telegram=Telegram(self.service,None,'synthetic-token')
        telegram.bot={'id':100,'username':'TestBot','first_name':'Alba'}
        methods=[]
        async def unavailable(method,payload=None):
            methods.append(method)
            if method.startswith('setMy'): raise ValueError('Temporary rate limit')
            return True
        telegram.api=unavailable
        await telegram.configure_bot()
        self.assertNotIn('setMyName',methods)
        self.assertIn('deleteWebhook',methods)
        self.assertEqual(self.store.setting('telegram_commands_version'),'')

    async def test_32_telegram_metadata_not_written_again_each_start(self):
        telegram=Telegram(self.service,None,'synthetic-token')
        telegram.bot={'first_name':'Alba'}
        self.store.set_setting('telegram_identity_configured',1)
        self.store.set_setting('telegram_commands_version','notte-20261004')
        methods=[]
        async def api(method,payload=None): methods.append(method); return True
        telegram.api=api; await telegram.configure_bot()
        self.assertEqual(methods,['deleteWebhook'])

    def test_33_reported_question_repetition_with_preface(self):
        recent=[{'role':'assistant','content':'Prima che ti spieghi cosa fare, vorrei solo chiederti: qual è esattamente la parte del gioco che più ti preoccupa?'}]
        result=remove_repeated_questions('Puoi cominciare da una cosa piccola. Qual è esattamente la parte del gioco che più ti preoccupa?',recent)
        self.assertNotIn('?',result)

    async def test_29_family_and_exam_memories_preserve_original_quotes(self):
        for text in ('Mia madre mi mette pressione per la patente','Sto studiando per l’esame di guida'):
            self.store.add_message(Scope('user',2),2,'user',text)
        await memory_cycle(self.store)
        content=[m['content'] for m in self.store.profile(2)]
        self.assertIn('Mia madre mi mette pressione per la patente',content)
        self.assertIn('Sto studiando per l’esame di guida',content)

    def test_30_restore_revokes_web_password(self):
        self.keys.set_web_password(2,2)
        snapshot=self.backups.create('manual'); target=self.settings.data/'restored.sqlite3'
        self.backups.restore(snapshot,target)
        restored=Store(target)
        try: self.assertEqual(restored.rows('SELECT * FROM web_credentials'),[])
        finally: restored.close()

    async def test_28_disk_real_and_schedule_validated(self):
        status,data=await self.request('/api/admin')
        self.assertEqual(status,200); self.assertGreater(data['disk']['total'],0)
        for value in ('24:00','23:60','garbage'):
            status,_=await self.request('/api/admin/action',{'action':'memory_schedule','night_time':value})
            self.assertEqual(status,403)
        status,_=await self.request('/api/admin/action',{'action':'memory_schedule','night_time':'22:30'})
        self.assertEqual(status,200); self.assertEqual(self.store.setting('memory_night_time'),'22:30')



    async def test_34_telegram_menu_includes_private_consent_and_feedback(self):
        telegram=Telegram(self.service,None,'synthetic-token')
        telegram.bot={'first_name':'Alba'}
        self.store.set_setting('telegram_identity_configured',1)
        menus=[]
        async def api(method,payload=None):
            if method=='setMyCommands': menus.append(payload['commands'])
            return True
        telegram.api=api
        await telegram.configure_bot()
        commands={entry['command'] for entry in menus[0]}
        self.assertTrue({'memory_key','feedback','web_key','export_key'}<=commands)



    async def test_35_explicit_revocation_survives_configured_user_restart(self):
        await self.request('/api/admin/users',{'action':'deny','user_id':'2'})
        restarted=Service(self.store,self.settings,self.keys,self.engine,self.backups)
        self.assertFalse(self.store.allowed(2))
        self.assertTrue(self.store.allowed(1))
        await restarted.handle(self.event('/web_key'))
        self.assertFalse(self.store.allowed(2))
        await self.request('/api/admin/users',{'action':'allow','user_id':'2'})
        self.assertTrue(self.store.allowed(2))

if __name__=='__main__': unittest.main()
