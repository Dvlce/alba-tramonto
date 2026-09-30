import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path
from datetime import datetime
from aiohttp.test_utils import TestClient,TestServer
from app import web_app
from backups import Backups
from config import Settings
from engine import Engine,repeated_response,RESPONSE_PROGRESS
from maintenance_tasks import memory_cycle,rework_memory,rework_scope
from runtime_features import Performance,quota,touch_activity,break_status,Capacity
from security import Keys,secret_file
from service import Service,Incoming
from store import Store,Scope
from telegram_bot import Telegram
from usage import ROME


class Response:
    status=200
    def __init__(self,model,payload): self.model,self.payload=model,payload
    async def __aenter__(self): return self
    async def __aexit__(self,*args): pass
    async def json(self):
        model=self.model; model.started.set(); await model.release.wait()
        if model.callback: model.callback()
        schema=self.payload['format']
        if 'selected_message_ids' in schema['properties']:
            ids=schema['properties']['selected_message_ids']['items']['enum']
            content={'selected_message_ids':model.selected if model.selected is not None else ids[:2]}
        else: content={'reply':'Proviamo a scegliere un piccolo passo concreto.','used_memory_ids':[],'personal_claims':[]}
        return {'message':{'content':json.dumps(content)},'prompt_eval_count':40,'eval_count':25}


class Model:
    def __init__(self):
        self.started=asyncio.Event(); self.release=asyncio.Event(); self.release.set()
        self.selected=None; self.callback=None; self.payloads=[]
    def post(self,url,json,**kwargs):
        self.payloads.append(json)
        return Response(self,json)


class WellbeingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.settings=Settings(root=Path(self.tmp.name),admins=(1,),allowed=(2,3),public_url='https://example.test')
        self.store=Store(self.settings.data/'alba.sqlite3'); self.keys=Keys(self.store,secret_file(self.settings.data/'auth.key'))
        self.model=Model(); self.engine=Engine(self.store,self.settings,self.model)
        self.service=Service(self.store,self.settings,self.keys,self.engine,Backups(self.store,self.settings))
        for uid,name in ((1,'Admin'),(2,'Alice'),(3,'Bob')): self.store.register(uid,name)
    def tearDown(self): self.store.close(); self.tmp.cleanup()
    def event(self,text,uid=2,kind='private',chat=None,transport='telegram'):
        return Incoming(uid,self.store.user_name(uid),chat or uid,kind,text,mention_bot=True,transport=transport)
    def message(self,text='Voglio prendere la patente',uid=2,scope=None):
        return self.store.add_message(scope or Scope('user',uid),uid,'user',text)
    async def request(self,path,body=None,uid=1,csrf=True):
        cookie,token=self.keys.session(self.keys.issue(uid,uid,'web'))
        client=TestClient(TestServer(web_app(self.service))); await client.start_server()
        headers={'Cookie':'session='+cookie}
        if csrf: headers['X-CSRF-Token']=token
        try:
            response=await (client.post(path,json=body,headers=headers) if body is not None else client.get(path,headers=headers))
            return response.status,await response.json()
        finally: await client.close()

    def test_01_break_after_continuous_twenty_minutes(self):
        for stamp in range(1000,2201,240): notice=touch_activity(self.store,2,stamp)
        self.assertIsNotNone(notice); self.assertGreater(len(notice['message']),60)

    def test_02_break_not_for_tab_open_without_interaction(self):
        touch_activity(self.store,2,1000)
        self.assertIsNone(break_status(self.store,2,2200))
        self.assertIsNone(touch_activity(self.store,2,2200))

    def test_03_break_does_not_repeat_on_poll_or_each_message(self):
        for stamp in range(1000,2201,240): touch_activity(self.store,2,stamp)
        first=break_status(self.store,2,2200)
        self.assertEqual(first,touch_activity(self.store,2,2205))
        self.assertIsNone(break_status(self.store,3,2205))

    def test_04_break_configurable_and_erase(self):
        self.store.set_setting('break_minutes',5)
        touch_activity(self.store,2,1000); self.assertIsNotNone(touch_activity(self.store,2,1300))
        self.store.forget_user(2); self.assertEqual(self.store.rows('SELECT * FROM user_activity'),[])

    async def test_05_crisis_has_no_break_or_quota_block(self):
        self.store.execute('INSERT INTO user_limits VALUES(2,1)')
        self.store.record_tokens(Scope('user',2),2,'test','ollama',5,5)
        touch_activity(self.store,2); result=await self.service.handle(self.event('Voglio suicidarmi'))
        self.assertIn('sicurezza',result.text); self.assertIsNone(result.break_notice)
        self.assertEqual(self.store.rows('SELECT * FROM user_activity'),[])

    def test_06_quota_counts_private_web_and_group_for_sender(self):
        self.store.execute('INSERT INTO user_limits VALUES(2,100)')
        for scope in (Scope('user',2),Scope('group',-10)): self.store.record_tokens(scope,2,'test','ollama',30,25)
        self.store.record_tokens(Scope('user',3),3,'test','ollama',900,100)
        self.assertEqual(quota(self.store,2)['used'],110); self.assertTrue(quota(self.store,2)['exhausted'])
        self.assertFalse(quota(self.store,3)['exhausted'])

    def test_07_quota_resets_at_rome_month_boundary(self):
        self.store.execute('INSERT INTO user_limits VALUES(2,100)')
        self.store.record_tokens(Scope('user',2),2,'test','ollama',100,20,timestamp=datetime(2026,9,30,23,59,tzinfo=ROME).timestamp())
        self.assertTrue(quota(self.store,2,datetime(2026,9,30,23,59,tzinfo=ROME))['exhausted'])
        self.assertEqual(quota(self.store,2,datetime(2026,10,1,0,0,tzinfo=ROME))['used'],0)

    async def test_08_quota_stops_next_generation_not_reading_memory(self):
        self.store.execute('INSERT INTO user_limits VALUES(2,50)')
        first=await self.service.handle(self.event('Vorrei organizzarmi'))
        self.assertIn('piccolo passo',first.text)
        second=await self.service.handle(self.event('Vorrei altre idee'))
        self.assertIn('limite mensile',second.text); self.assertEqual(len(self.model.payloads),1)
        memory=await self.service.handle(self.event('/memory')); self.assertNotIn('limite mensile',memory.text)

    async def test_09_queued_requests_cannot_skip_exhausted_quota(self):
        self.store.execute('INSERT INTO user_limits VALUES(2,50)'); self.store.execute('INSERT INTO groups(id,enabled) VALUES(-10,1)')
        self.model.release.clear()
        first=asyncio.create_task(self.service.handle(self.event('Una scelta privata')))
        await self.model.started.wait()
        second=asyncio.create_task(self.service.handle(self.event('Una scelta pubblica',kind='group',chat=-10)))
        await asyncio.sleep(.01); self.model.release.set()
        results=await asyncio.gather(first,second)
        self.assertEqual(len(self.model.payloads),1); self.assertIn('limite mensile',results[1].text)

    def test_10_unknown_tokens_are_flagged_without_estimates(self):
        self.store.record_tokens(Scope('user',2),2,'test','ollama',None,None)
        q=quota(self.store,2); self.assertEqual(q['used'],0); self.assertEqual(q['unreported'],1)

    async def test_11_limits_admin_only_and_audited(self):
        status,_=await self.request('/api/admin/users',{'action':'token_limit','user_id':'2','token_limit':1000},uid=2)
        self.assertEqual(status,403)
        status,_=await self.request('/api/admin/users',{'action':'token_limit','user_id':'2','token_limit':1000})
        self.assertEqual(status,200); self.assertEqual(quota(self.store,2)['limit'],1000)
        self.assertTrue(self.store.rows("SELECT * FROM audit_logs WHERE action='web_token_limit' AND target_id=2"))

    async def test_12_limits_validation_and_csrf(self):
        for limit in (-1,True,1.2,'100',10**13):
            status,_=await self.request('/api/admin/users',{'action':'token_limit','user_id':2,'token_limit':limit})
            self.assertEqual(status,400)
        status,_=await self.request('/api/admin/users',{'action':'token_limit','user_id':2,'token_limit':500},csrf=False)
        self.assertEqual(status,403)

    async def test_13_status_does_not_leak_other_users(self):
        self.store.record_tokens(Scope('user',3),3,'test','ollama',900,100)
        self.service.maintenance.update(running=True,message='Riordino della memoria')
        status,data=await self.request('/api/status',uid=2)
        self.assertEqual(status,200); self.assertEqual(data['quota']['used'],0)
        self.assertNotIn('user:3',str(data)); self.assertIn('disk',data['performance'])

    async def test_14_web_key_button_fragment_one_use_owner(self):
        result=await self.service.handle(self.event('/web_key'))
        self.assertTrue(result.login_url.startswith('https://example.test/#web_key='))
        token=result.login_url.split('=',1)[1]; cookie,_=self.keys.session(token)
        self.assertEqual(self.keys.identify(cookie)['user_id'],2)
        with self.assertRaises(PermissionError): self.keys.session(token)
        self.assertNotIn(token,str(self.store.rows('SELECT * FROM audit_logs')))

    async def test_15_telegram_button_delivery_without_preview(self):
        telegram=Telegram(self.service,None,'synthetic'); calls=[]
        async def api(method,payload): calls.append((method,payload)); return {}
        telegram.api=api
        event=self.event('/web_key'); await telegram.deliver(event,await self.service.handle(event))
        payload=calls[0][1]; self.assertTrue(payload['protect_content'])
        self.assertIn('#web_key=',payload['reply_markup']['inline_keyboard'][0][0]['url'])
        self.assertTrue(payload['link_preview_options']['is_disabled'])

    async def test_16_summary_contains_only_original_scoped_quotes(self):
        private=self.message('Preferisco risposte brevi'); other=self.message('Segreto di Bob',uid=3)
        await rework_scope(self.service,Scope('user',2))
        result=self.store.rows("SELECT * FROM summaries WHERE summary_kind='consolidated'")[0]
        quotes=json.loads(result['content']); self.assertEqual(quotes[0]['quote'],'Preferisco risposte brevi')
        self.assertEqual(json.loads(result['source_ids']),[private]); self.assertNotIn('Segreto di Bob',str(result))
        self.assertEqual(quota(self.store,2)['used'],0); self.assertEqual(quota(self.store,0)['used'],65)

    async def test_17_group_summary_never_reads_private_context(self):
        self.message('Informazione privata di Alice'); self.message('Evento pubblico',scope=Scope('group',-10))
        self.message('Evento pubblico di Bob',uid=3,scope=Scope('group',-10))
        await rework_scope(self.service,Scope('group',-10))
        sent=str(self.model.payloads[0]); self.assertNotIn('Informazione privata',sent)
        row=self.store.rows("SELECT * FROM summaries WHERE scope='group:-10'")[0]
        self.assertEqual({q['user_id'] for q in json.loads(row['content'])},{2,3})

    async def test_18_model_cannot_invent_or_cross_scope_summary_sources(self):
        self.message(); other=self.message('Segreto di Bob',uid=3); self.model.selected=[other]
        with self.assertRaises(ValueError): await rework_scope(self.service,Scope('user',2))
        self.assertEqual(self.store.rows("SELECT * FROM summaries WHERE summary_kind='consolidated'"),[])

    async def test_19_summary_rechecks_deletion_after_model(self):
        mid=self.message(); self.model.callback=lambda:self.store.execute('DELETE FROM messages WHERE id=?',(mid,))
        self.assertFalse(await rework_scope(self.service,Scope('user',2)))
        self.assertEqual(self.store.rows('SELECT * FROM summaries'),[])

    async def test_20_foreground_interrupts_background_rework(self):
        self.message(); await memory_cycle(self.store); self.model.release.clear()
        task=asyncio.create_task(rework_memory(self.service)); self.service.maintenance_task=task
        await self.model.started.wait(); self.assertTrue(self.service.maintenance['running'])
        result=await self.service.handle(self.event('/memory'))
        self.assertTrue(task.cancelled()); self.assertFalse(self.service.maintenance['running'])
        self.assertFalse(self.engine.lock.locked()); self.assertIn('patente',result.text)

    async def test_21_rework_idempotent_no_extra_model_calls(self):
        self.message(); self.assertEqual(await rework_memory(self.service),1)
        self.assertEqual(await rework_memory(self.service),0); self.assertEqual(len(self.model.payloads),1)

    async def test_22_rework_notice_and_state_cleanup_on_failure(self):
        self.message(); notices=[]
        async def notify(): notices.append(self.service.maintenance['message'])
        self.service.maintenance_notify=notify; self.model.selected=[999]
        with self.assertRaises(ValueError): await rework_memory(self.service)
        self.assertEqual(len(notices),1); self.assertFalse(self.service.maintenance['running'])
        self.assertNotIn('patente',notices[0])

    def test_23_performance_measures_cpu_deltas_and_available_ram(self):
        proc=Path(self.tmp.name)/'proc'; proc.mkdir()
        (proc/'stat').write_text('cpu  100 0 100 800 0 0 0 0\n')
        (proc/'meminfo').write_text('MemTotal: 8000 kB\nMemAvailable: 5000 kB\n')
        perf=Performance(self.settings.root,proc=proc)
        (proc/'stat').write_text('cpu  125 0 125 850 0 0 0 0\n')
        data=perf.sample(); self.assertEqual(data['cpu_percent'],50)
        self.assertEqual(data['ram']['percent'],37.5); self.assertGreater(data['disk']['total'],0)

    async def test_24_policies_public_and_edit_requires_admin(self):
        client=TestClient(TestServer(web_app(self.service))); await client.start_server()
        try:
            response=await client.get('/policy-info'); self.assertEqual(response.status,200)
            self.assertEqual((await response.json())['owner'],'Gestore Alba')
            response=await client.get('/api/status'); self.assertEqual(response.status,403)
        finally: await client.close()
        status,_=await self.request('/api/admin/action',{'action':'privacy','owner':'Gestore','contact':'mail@example.test'},uid=2)
        self.assertEqual(status,403)
        status,_=await self.request('/api/admin/action',{'action':'privacy','owner':'Gestore','contact':'mail@example.test'})
        self.assertEqual(status,200); self.assertEqual(self.store.setting('privacy_owner'),'Gestore')

    async def test_25_break_interval_range_and_private_commands(self):
        for minutes in (4,121,True,'20'):
            status,_=await self.request('/api/admin/action',{'action':'break_interval','minutes':minutes})
            self.assertEqual(status,403)
        status,_=await self.request('/api/admin/action',{'action':'break_interval','minutes':25})
        self.assertEqual(status,200)
        result=await self.service.handle(self.event('/privacy')); self.assertIn('https://example.test/privacy',result.text)

    async def test_26_forget_removes_background_personal_accounting(self):
        self.message(); await rework_scope(self.service,Scope('user',2))
        self.assertEqual(quota(self.store,0)['used'],65); self.store.forget_user(2)
        self.assertEqual(self.store.rows('SELECT * FROM token_usage'),[])

    async def test_27_revoked_owner_gets_no_new_summary(self):
        self.message(); self.model.callback=lambda:self.store.execute('UPDATE users SET authorized=0 WHERE id=2')
        self.assertFalse(await rework_scope(self.service,Scope('user',2)))
        self.assertEqual(self.store.rows('SELECT * FROM summaries'),[])

    def test_28_twenty_accounts_five_presence_slots(self):
        for uid in range(4,21): self.store.authorize(uid,20)
        with self.assertRaises(ValueError): self.store.authorize(21,20)
        cap=Capacity(5)
        for uid in range(1,6): self.assertTrue(cap.enter(uid,now=100)['admitted'])
        sixth=cap.enter(6,now=100); self.assertFalse(sixth['admitted']); self.assertEqual(sixth['position'],1)

    def test_29_same_identity_web_and_telegram_uses_one_slot(self):
        cap=Capacity(5); cap.enter(2,now=100); cap.enter(2,now=120)
        self.assertEqual(cap.status(2,now=120)['online'],1)

    def test_30_waiting_order_and_slot_released(self):
        cap=Capacity(1); cap.enter(1,now=100); cap.enter(2,now=100); cap.enter(3,now=100)
        cap.leave(1)
        self.assertFalse(cap.enter(3,now=120)['admitted'])
        self.assertTrue(cap.enter(2,now=120)['admitted'])

    def test_31_presence_expires_but_active_inference_retains_slot(self):
        cap=Capacity(1,ttl=90); cap.enter(1,now=100)
        self.assertFalse(cap.enter(2,now=200,active=(1,))['admitted'])
        self.assertTrue(cap.enter(2,now=201)['admitted'])

    async def test_32_sixth_chat_gets_wait_notice_and_message_saved(self):
        for uid in range(10,15): self.service.capacity.enter(uid)
        result=await self.service.handle(self.event('Mi chiamo Alice'))
        self.assertIn('Aspetta',result.text); self.assertEqual(len(self.model.payloads),0)
        self.assertEqual(self.store.recent(Scope('user',2))[-1]['content'],'Mi chiamo Alice')
        self.assertIn('Alice',str(self.store.profile(2)))

    async def test_33_full_room_allows_data_commands_and_crisis(self):
        for uid in range(10,15): self.service.capacity.enter(uid)
        self.assertNotIn('Aspetta',(await self.service.handle(self.event('/memory'))).text)
        result=await self.service.handle(self.event('Voglio suicidarmi'))
        self.assertIn('sicurezza',result.text); self.assertEqual(len(self.model.payloads),0)

    async def test_34_history_unified_private_namespace_across_transports(self):
        await self.service.handle(self.event('Mi chiamo Alice',transport='telegram'))
        await self.service.handle(self.event('Preferisco risposte brevi',transport='web'))
        status,data=await self.request('/api/history',uid=2)
        self.assertEqual(status,200); self.assertEqual(len(data['messages']),4)
        self.assertIn('Alice',str(self.store.profile(2))); self.assertIn('brevi',str(self.store.profile(2)))
        status,other=await self.request('/api/history',uid=3); self.assertEqual(other['messages'],[])

    async def test_35_incremental_history_scoped_and_validation(self):
        old=self.message(); new=self.message('Nuovo messaggio Telegram'); self.message('Segreto Bob',uid=3)
        status,data=await self.request('/api/history?after='+str(old),uid=2)
        self.assertEqual([r['id'] for r in data['messages']],[new])
        status,_=await self.request('/api/history?after=-1',uid=2); self.assertEqual(status,403)

    async def test_36_presence_endpoint_csrf_and_cannot_choose_owner(self):
        status,_=await self.request('/api/presence',{},uid=2,csrf=False); self.assertEqual(status,403)
        status,data=await self.request('/api/presence',{'user_id':3},uid=2)
        self.assertEqual(status,200); self.assertTrue(data['admitted'])
        self.assertNotIn(3,self.service.capacity.leases); self.assertIn(2,self.service.capacity.leases)

    def test_37_whole_replies_and_shortened_paragraphs_detected(self):
        old='Capisco perfettamente il tuo pensiero. La pressione della madre può essere pesante quando si hanno obiettivi importanti come una patente o un esame in arrivo. Forse puoi raccontarmi brevemente di quella situazione per capire meglio il tuo punto di vista.'
        rows=[{'role':'assistant','content':old}]
        self.assertTrue(repeated_response(old,rows))
        self.assertTrue(repeated_response(old.replace('Capisco perfettamente il tuo pensiero. ',''),rows))
        self.assertFalse(repeated_response('Per la demo scegli una scena giocabile e rinvia le funzioni secondarie; prepara una lista di tre cose indispensabili.',rows))

    async def test_38_repeated_model_output_retried_then_rejected(self):
        old='Proviamo a scegliere un piccolo passo concreto. Poi organizziamo il tempo in una lista di cose da fare oggi.'
        self.store.add_message(Scope('user',2),None,'assistant',old)
        async def generate(messages):
            return {'reply':old,'used_memory_ids':[],'personal_claims':[]}
        self.engine.generate=generate
        result=await self.service.handle(self.event('La mia priorità è pubblicare la demo'))
        self.assertNotEqual(result.text,old); self.assertIn('demo',result.text)

    async def test_39_model_receives_latest_message_as_actual_user_turn(self):
        self.message('Mia madre vuole che vada a judo')
        self.store.add_message(Scope('user',2),None,'assistant','Capisco perfettamente il tuo pensiero. Forse puoi raccontarmi brevemente la situazione.')
        await self.service.handle(self.event('Voglio pubblicare la demo prima dell’università'))
        messages=self.model.payloads[-1]['messages']
        self.assertEqual(messages[-1]['content'],'Voglio pubblicare la demo prima dell’università')
        self.assertEqual(messages[-1]['role'],'user')
        self.assertNotIn('Capisco perfettamente il tuo pensiero',str(messages))

    async def test_40_group_prompt_only_group_memory_and_attributed_turns(self):
        self.message('Segreto privato di Alice'); self.store.execute('INSERT INTO groups(id,enabled) VALUES(-10,1)')
        self.message('Vorrei organizzare un incontro',uid=3,scope=Scope('group',-10))
        await self.service.handle(self.event('Come organizziamo un incontro?',kind='group',chat=-10))
        payload=str(self.model.payloads[-1]); self.assertNotIn('Segreto privato',payload); self.assertIn('user_id=3',payload)

    async def test_41_natural_personal_declarations_update_profile(self):
        result=await self.service.handle(self.event('Secondo te, mia madre vuole mandarmi a judo in modo "obbligatorio" ma io voglio creare il mio gioco'))
        self.assertTrue(self.store.rows("SELECT * FROM memories WHERE scope='user:2' AND category='relationship'"))
        await self.service.handle(self.event('Diciamo io voglio pubblicare la demo prima dell’università'))
        self.assertTrue(self.store.rows("SELECT * FROM memories WHERE scope='user:2' AND category='goal'"))

    async def test_42_quoted_first_person_is_not_a_private_fact(self):
        for text in ('"Mi chiamo Bob"','Mario dice "mi chiamo Bob"','«Voglio pubblicare la demo»'):
            mid=self.message(text); await memory_cycle(self.store)
        self.assertEqual(self.store.profile(2),[])

    async def test_43_avatar_cannot_choose_another_user(self):
        calls=[]
        async def photo(uid): calls.append(uid); return b'\xff\xd8\xffsynthetic-jpeg'
        self.service.telegram_avatar=photo
        cookie,_=self.keys.session(self.keys.issue(2,2,'web'))
        client=TestClient(TestServer(web_app(self.service))); await client.start_server()
        try:
            headers={'Cookie':'session='+cookie}
            response=await client.get('/api/avatar?user_id=3',headers=headers); self.assertEqual(response.status,403)
            response=await client.get('/api/avatar',headers=headers); self.assertEqual(response.status,200)
            self.assertEqual(calls,[2]); self.assertEqual(await response.read(),b'\xff\xd8\xffsynthetic-jpeg')
            response=await client.get('/api/avatar',headers=headers); self.assertEqual(response.status,200); self.assertEqual(calls,[2])
        finally: await client.close()
        self.store.forget_user(2); self.assertEqual(self.store.rows('SELECT * FROM user_avatars'),[])

    async def test_44_avatar_not_resurrected_after_erasure_during_fetch(self):
        async def photo(uid): self.store.forget_user(uid); return b'\xff\xd8\xffsynthetic'
        self.service.telegram_avatar=photo
        cookie,_=self.keys.session(self.keys.issue(2,2,'web'))
        client=TestClient(TestServer(web_app(self.service))); await client.start_server()
        try:
            response=await client.get('/api/avatar',headers={'Cookie':'session='+cookie})
            self.assertEqual(response.status,204); self.assertEqual(self.store.rows('SELECT * FROM user_avatars'),[])
        finally: await client.close()

    async def test_45_profile_uncertainty_distinct_and_style_changes_historical(self):
        await self.service.handle(self.event('Forse voglio pubblicare la demo'))
        profile=await self.service.handle(self.event('/profile'))
        self.assertIn('[INCERTO]',profile.text); self.assertEqual(self.store.profile(2),[])
        await self.service.handle(self.event('Preferisco risposte brevi'))
        await self.service.handle(self.event('Preferisco risposte dettagliate'))
        current=self.store.profile(2)
        self.assertTrue(any('dettagliate' in r['content'] for r in current))
        self.assertFalse(any('brevi' in r['content'] for r in current))
        old=self.store.memories(Scope('user',2),historical=True)
        self.assertTrue(any('brevi' in r['content'] and r['status']=='historical' for r in old))


    async def test_46_complete_history_pages_are_ordered_and_private(self):
        ids=[]
        for index in range(123):
            ids.append(self.message('Nota di Alice '+str(index)))
            self.message('Nota privata di Bob '+str(index),uid=3)
            self.message('Nota del gruppo '+str(index),scope=Scope('group',-10))
        status,page=await self.request('/api/history',uid=2)
        self.assertEqual(status,200); self.assertTrue(page['has_older'])
        self.assertEqual([r['id'] for r in page['messages']],ids[-50:])
        complete=page['messages']; cursor=page['next_before']
        while page['has_older']:
            _,page=await self.request('/api/history?before='+str(cursor),uid=2)
            self.assertLess(len(page['messages']),51)
            self.assertTrue(all(r['id']<cursor for r in page['messages']))
            cursor=page['next_before']; complete=page['messages']+complete
        self.assertEqual([r['id'] for r in complete],ids)
        self.assertNotIn('Bob',str(complete)); self.assertNotIn('gruppo',str(complete))

    async def test_47_history_cursor_validation_and_owner_forgery(self):
        self.message('Segreto di Bob',uid=3)
        for query in ('before=0','before=-1','before=1.5','before=9223372036854775808',
                      'after=1&before=2','before=1&before=2','after=1&after=2',
                      'user_id=3','scope=user:3','group_id=-10','before='):
            status,_=await self.request('/api/history?'+query,uid=2)
            self.assertEqual(status,403,query)

    async def test_48_new_telegram_messages_sync_after_paging_without_duplicates(self):
        original=[self.message('Messaggio '+str(index)) for index in range(80)]
        _,latest=await self.request('/api/history',uid=2)
        _,older=await self.request('/api/history?before='+str(latest['next_before']),uid=2)
        self.message('Segreto di Bob',uid=3)
        incoming=self.message('Nuovo messaggio Telegram')
        _,new=await self.request('/api/history?after='+str(original[-1]),uid=2)
        all_rows=older['messages']+latest['messages']+new['messages']
        self.assertEqual([row['id'] for row in all_rows],original+[incoming])
        self.assertFalse(older['has_older']); self.assertEqual(len(new['messages']),1)

    async def test_49_job_progress_is_owner_scoped_and_model_queue_is_real(self):
        self.model.release.clear(); await self.engine.lock.acquire()
        client=TestClient(TestServer(web_app(self.service))); await client.start_server()
        def headers(uid):
            cookie,csrf=self.keys.session(self.keys.issue(uid,uid,'web'))
            return {'Cookie':'session='+cookie,'X-CSRF-Token':csrf}
        alice,bob=headers(2),headers(3); running=[]
        try:
            response=await client.post('/api/chat',json={'message':'Consiglio per Alice'},headers=alice)
            first=(await response.json())['job_id']; running.append((first,alice))
            response=await client.post('/api/chat',json={'message':'Consiglio per Bob'},headers=bob)
            second=(await response.json())['job_id']; running.append((second,bob))
            response=await client.get('/api/jobs/'+first,headers=alice); progress=await response.json()
            self.assertEqual(progress['phase'],'queued'); self.assertTrue(progress['pending'])
            self.assertGreaterEqual(progress['elapsed_seconds'],0)
            response=await client.get('/api/jobs/'+first,headers=bob); self.assertEqual(response.status,403)
            self.engine.lock.release(); await asyncio.wait_for(self.model.started.wait(),1)
            response=await client.get('/api/jobs/'+first,headers=alice); self.assertEqual((await response.json())['phase'],'generating')
            response=await client.get('/api/jobs/'+second,headers=bob); self.assertEqual((await response.json())['phase'],'queued')
            response=await client.post('/api/jobs/'+first+'/cancel',json={},headers=alice)
            self.assertTrue((await response.json())['cancelled'])
            response=await client.get('/api/jobs/'+second,headers=bob); self.assertEqual((await response.json())['phase'],'generating')
        finally:
            for job,auth in running: await client.post('/api/jobs/'+job+'/cancel',json={},headers=auth)
            if self.engine.lock.locked(): self.engine.lock.release()
            await client.close()
        self.assertIsNone(RESPONSE_PROGRESS.get())
        self.assertFalse(self.service.active_responses)

    async def test_50_stop_while_waiting_for_unified_conversation_lock(self):
        lock=self.service.scope_locks.setdefault('user:2',asyncio.Lock()); await lock.acquire()
        client=TestClient(TestServer(web_app(self.service))); await client.start_server()
        cookie,csrf=self.keys.session(self.keys.issue(2,2,'web'))
        headers={'Cookie':'session='+cookie,'X-CSRF-Token':csrf}
        try:
            response=await client.post('/api/chat',json={'message':'Richiesta dal sito'},headers=headers)
            job=(await response.json())['job_id']
            response=await client.get('/api/jobs/'+job,headers=headers)
            self.assertEqual((await response.json())['phase'],'queued'); self.assertFalse(self.model.payloads)
            response=await client.post('/api/jobs/'+job+'/cancel',json={},headers=headers)
            self.assertTrue((await response.json())['cancelled'])
            response=await client.get('/api/jobs/'+job,headers=headers)
            self.assertTrue((await response.json())['cancelled']); self.assertTrue(lock.locked())
        finally: lock.release(); await client.close()
        self.assertIsNone(RESPONSE_PROGRESS.get())

    async def test_51_erased_messages_cannot_reappear_through_pagination(self):
        for index in range(70): self.message('Da cancellare '+str(index))
        self.message('Segreto da mantenere',uid=3)
        _,history=await self.request('/api/history',uid=2); cursor=history['next_before']
        self.store.forget_user(2)
        for path in ('/api/history','/api/history?before='+str(cursor),'/api/history?after=0'):
            status,data=await self.request(path,uid=2)
            self.assertEqual(status,200); self.assertEqual(data['messages'],[])
        self.assertTrue(self.store.recent(Scope('user',3)))

    async def test_52_completed_job_cache_does_not_block_long_sessions(self):
        client=TestClient(TestServer(web_app(self.service))); await client.start_server()
        cookie,csrf=self.keys.session(self.keys.issue(2,2,'web'))
        headers={'Cookie':'session='+cookie,'X-CSRF-Token':csrf}; tickets=[]
        try:
            for _ in range(120):
                response=await client.post('/api/chat',json={'message':'/help'},headers=headers)
                self.assertEqual(response.status,202)
                ticket=(await response.json())['job_id']; tickets.append(ticket)
                response=await client.get('/api/jobs/'+ticket,headers=headers); result=await response.json()
                self.assertIn('/profile',result['reply'])
            response=await client.get('/api/jobs/'+tickets[0],headers=headers); self.assertEqual(response.status,403)
            response=await client.get('/api/jobs/'+tickets[-1],headers=headers); self.assertEqual(response.status,200)
            self.assertFalse(self.model.payloads)
        finally: await client.close()

    async def test_53_job_cache_eviction_preserves_active_generation(self):
        self.model.release.clear()
        client=TestClient(TestServer(web_app(self.service))); await client.start_server()
        def headers(uid):
            cookie,csrf=self.keys.session(self.keys.issue(uid,uid,'web'))
            return {'Cookie':'session='+cookie,'X-CSRF-Token':csrf}
        alice,bob=headers(2),headers(3); ticket=None
        try:
            response=await client.post('/api/chat',json={'message':'Consigli per il progetto'},headers=alice)
            ticket=(await response.json())['job_id']; await asyncio.wait_for(self.model.started.wait(),1)
            for _ in range(110):
                response=await client.post('/api/chat',json={'message':'/help'},headers=bob)
                self.assertEqual(response.status,202)
                other=(await response.json())['job_id']
                response=await client.get('/api/jobs/'+other,headers=bob)
                self.assertIn('/profile',(await response.json())['reply'])
            response=await client.get('/api/jobs/'+ticket,headers=alice)
            self.assertEqual(response.status,200); self.assertEqual((await response.json())['phase'],'generating')
        finally:
            if ticket: await client.post('/api/jobs/'+ticket+'/cancel',json={},headers=alice)
            await client.close()
        self.assertFalse(self.engine.lock.locked())


if __name__=='__main__': unittest.main()
