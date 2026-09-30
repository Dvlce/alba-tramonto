import asyncio
import json
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from config import Settings
from store import Store,Scope
from memory import evaluate_memories,retrieve,build_context,summarize
from security import Keys,secret_file
from exports import export_document,personal_bundle,generate_persona
from backups import Backups
from engine import Engine,validate_response
from service import Service,Incoming
from telegram_bot import normalize
from app import web_app


class FakeEngine(Engine):
    async def generate(self,messages):
        return {'reply':'Capisco. Qual è la cosa che pesa di più in questo momento?',
                'used_memory_ids':[],'personal_claims':[]}


class SystemTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.settings=Settings(root=self.root,admins=(1,),allowed=(2,3))
        self.store=Store(self.settings.data/'alba.sqlite3')
        self.keys=Keys(self.store,secret_file(self.settings.data/'auth.key'))
        self.backups=Backups(self.store,self.settings)
        self.engine=FakeEngine(self.store,self.settings,None)
        self.service=Service(self.store,self.settings,self.keys,self.engine,self.backups)
        for uid,name in [(1,'Admin'),(2,'Alice'),(3,'Bob')]:
            self.store.register(uid,name)
        for gid in (-10,-20):
            self.store.execute('INSERT INTO groups VALUES(?,1,0,0)',(gid,))
        async def yes(*args):return True
        self.service.group_admin_check=yes

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def event(self,text,uid=2,group=None,**kw):
        return Incoming(uid,self.store.user_name(uid),group or uid,
                        'group' if group else 'private',text,**kw)

    def remember(self,text='Mi chiamo Alice',uid=2,group=None,evidence='fact',expires=None):
        scope=Scope('group',group) if group else Scope('user',uid)
        mid=self.store.add_message(scope,uid,'user',text)
        mem=self.store.add_memory(scope,text,'personal' if not group else 'group',[mid],
                                  evidence=evidence,expires=expires)
        return mid,mem

    async def test_01_private_memory_persists(self):
        await self.service.handle(self.event('Mi chiamo Alice'))
        self.assertEqual(self.store.profile(2)[0]['content'],'Mi chiamo Alice')

    def test_02_user_retrieval_isolation(self):
        self.remember();self.remember('Mi chiamo Bob',uid=3)
        rows=retrieve(self.store,Scope('user',2),'nome')
        self.assertEqual([r['content'] for r in rows],['Mi chiamo Alice'])

    def test_03_private_data_not_in_group_context(self):
        self.remember('Mi chiamo SEGRETO_ALICE')
        ctx=build_context(self.store,Scope('group',-10),'nome')
        self.assertNotIn('SEGRETO_ALICE',json.dumps(ctx))

    def test_04_groups_are_isolated(self):
        self.remember('Evento gruppo segreto',group=-20)
        self.assertEqual(retrieve(self.store,Scope('group',-10),'evento'),[])

    def test_05_group_not_in_private_profile(self):
        self.remember('Mi chiamo Pubblico',group=-10)
        self.assertEqual(self.store.profile(2),[])

    def test_06_source_scope_must_match(self):
        mid,_=self.remember()
        with self.assertRaises(ValueError):
            self.store.add_memory(Scope('group',-10),'Mi chiamo Alice','group',[mid])

    def test_07_fact_must_be_original_quote(self):
        mid,_=self.remember()
        with self.assertRaises(ValueError):
            self.store.add_memory(Scope('user',2),'Alice è depressa','personal',[mid])

    def test_08_assistant_not_a_fact_source(self):
        mid=self.store.add_message(Scope('user',2),2,'assistant','Mi chiamo Alice')
        with self.assertRaises(ValueError):
            self.store.add_memory(Scope('user',2),'Mi chiamo Alice','personal',[mid])

    def test_09_inference_excluded_from_profile(self):
        self.remember('Possibile interesse',evidence='inference')
        self.assertEqual(self.store.profile(2),[])

    def test_10_temporary_expires(self):
        self.remember('Mi chiamo temporaneo',expires=time.time()-1)
        self.assertEqual(retrieve(self.store,Scope('user',2),'temporaneo'),[])

    async def test_11_not_every_message_is_memory(self):
        await self.service.handle(self.event('Ciao, come va'))
        self.assertEqual(self.store.memories(Scope('user',2)),[])

    async def test_12_question_not_a_fact(self):
        await self.service.handle(self.event('Mi chiamo Alice?'))
        self.assertEqual(self.store.profile(2),[])

    async def test_13_quote_not_a_personal_fact(self):
        await self.service.handle(self.event('Mario dice "Mi chiamo Alice"'))
        self.assertEqual(self.store.profile(2),[])

    async def test_14_uncertain_stays_uncertain(self):
        await self.service.handle(self.event('Forse mi piace correre'))
        rows=self.store.memories(Scope('user',2))
        self.assertEqual(rows[0]['evidence'],'uncertain')
        self.assertEqual(self.store.profile(2),[])

    def test_15_historical_changes_retained(self):
        self.remember('Mi chiamo Alice');self.remember('Mi chiamo Ada')
        rows=self.store.memories(Scope('user',2),historical=True)
        self.assertEqual({m['status'] for m in rows},{'historical','active'})

    def test_16_long_context_bounded(self):
        for i in range(180):
            self.store.add_message(Scope('user',2),2,'user','messaggio '+str(i)+' X'*600)
        context=build_context(self.store,Scope('user',2),'messaggio',budget=2500)
        self.assertLessEqual(len(json.dumps(context,ensure_ascii=False)),2500)

    def test_17_summaries_provenance_and_scope(self):
        for i in range(15):self.store.add_message(Scope('user',2),2,'user',f'episodio {i}')
        summarize(self.store,Scope('user',2))
        rows=self.store.rows('SELECT * FROM summaries')
        self.assertEqual(rows[0]['scope'],'user:2')
        self.assertEqual(len(json.loads(rows[0]['source_ids'])),15)

    def test_18_no_retrieval_query_injection(self):
        self.remember()
        self.assertEqual(retrieve(self.store,Scope('group',-10),'" OR 1=1 -- nome'),[])

    async def test_19_unknown_memory_says_missing(self):
        result=await self.service.handle(self.event('Ti ricordi il mio nome?'))
        self.assertEqual(result.text,'Non trovo questa informazione nella mia memoria.')

    async def test_20_known_recall_is_exact_quote(self):
        self.remember()
        result=await self.service.handle(self.event('Ti ricordi il mio nome?'))
        self.assertIn('«Mi chiamo Alice»',result.text)

    def test_21_generated_fake_memory_id_rejected(self):
        ctx={'memories':[]}
        self.assertIsNone(validate_response({'reply':'Ricordo Mario','used_memory_ids':[999],'personal_claims':[]},ctx))

    def test_22_unattributed_fake_recall_rejected(self):
        self.assertIsNone(validate_response({'reply':'Ricordo che hai una moglie','used_memory_ids':[],'personal_claims':[]},{'memories':[]}))

    def test_23_inference_not_presented_as_fact(self):
        ctx={'memories':[{'id':1,'content':'Forse correre','evidence':'inference'}]}
        payload={'reply':'Ricordo che corri','used_memory_ids':[1],'personal_claims':[{'memory_id':1,'quote':'Forse correre'}]}
        self.assertIsNone(validate_response(payload,ctx))

    async def test_24_diagnosis_is_informative_report(self):
        result=await self.service.handle(self.event('Dammi una diagnosi'))
        for word in ('non diagnosi','Osservazioni','Pattern','interpretazioni','mancanti','Domande','Limiti','Prossimi'):
            self.assertIn(word,result.text)

    async def test_25_crisis_gets_safety_response(self):
        result=await self.service.handle(self.event('Voglio suicidarmi'))
        self.assertIn('servizi di emergenza',result.text)
        self.assertNotIn('diagnosi',result.text)

    async def test_26_unauthorized_user_denied(self):
        result=await self.service.handle(self.event('ciao',uid=99))
        self.assertIn('autorizzarlo',result.text)
        self.assertEqual(self.store.recent(Scope('user',99)),[])

    async def test_27_max_users_limit(self):
        for uid in range(4,21):self.store.authorize(uid)
        with self.assertRaises(ValueError):self.store.authorize(21)

    async def test_28_group_private_profile_denied(self):
        self.remember()
        result=await self.service.handle(self.event('/profile',group=-10))
        self.assertIn('chat privata',result.text)
        self.assertNotIn('Mi chiamo Alice',result.text)

    async def test_29_export_key_only_private(self):
        result=await self.service.handle(self.event('/export_key',group=-10))
        self.assertIn('chat privata',result.text)
        self.assertEqual(self.store.rows('SELECT * FROM export_keys'),[])

    def test_30_token_random_and_hashed(self):
        a=self.keys.issue(2,2);b=self.keys.issue(2,2)
        self.assertNotEqual(a,b);self.assertGreaterEqual(len(a),40)
        self.assertNotIn(a,json.dumps(self.store.rows('SELECT * FROM export_keys')))
        self.assertNotIn(a,json.dumps(self.store.rows('SELECT * FROM audit_logs')))

    def test_31_user_a_cannot_export_b(self):
        self.remember('Mi chiamo Bob',uid=3)
        key=self.keys.issue(3,3)
        with self.assertRaises(PermissionError):export_document(self.store,self.keys,2,3,key)

    def test_32_other_owner_token_cannot_be_used(self):
        key=self.keys.issue(3,3)
        with self.assertRaises(PermissionError):export_document(self.store,self.keys,2,2,key)

    def test_33_key_one_use(self):
        key=self.keys.issue(2,2)
        export_document(self.store,self.keys,2,2,key)
        with self.assertRaises(PermissionError):export_document(self.store,self.keys,2,2,key)

    def test_34_key_expiry(self):
        key=self.keys.issue(2,2,ttl=-1)
        with self.assertRaises(PermissionError):self.keys.consume(2,2,key)

    def test_35_key_revocation(self):
        key=self.keys.issue(2,2);self.keys.revoke(2,2)
        with self.assertRaises(PermissionError):self.keys.consume(2,2,key)

    def test_36_web_key_not_export_key(self):
        key=self.keys.issue(2,2,'web')
        with self.assertRaises(PermissionError):export_document(self.store,self.keys,2,2,key)

    def test_37_export_no_group_or_other_user(self):
        self.remember();self.remember('Gruppo SEGRETO_GRUPPO',group=-10);self.remember('Mi chiamo SEGRETO_BOB',uid=3)
        name,body=export_document(self.store,self.keys,2,2,self.keys.issue(2,2))
        self.assertTrue(name.startswith('info_Alice'))
        self.assertIn('Mi chiamo Alice',body.decode())
        self.assertNotIn('SEGRETO_',body.decode())

    def test_38_export_separates_evidence(self):
        self.remember();self.remember('Ipotesi',evidence='inference');self.remember('Incerto',evidence='uncertain')
        bundle=personal_bundle(self.store,2)
        self.assertTrue(bundle['DATI_ORIGINALI'])
        self.assertEqual(bundle['INFERENZE'][0]['content'],'Ipotesi')
        self.assertEqual(bundle['INFORMAZIONI_INCERTE'][0]['content'],'Incerto')

    async def test_39_user_can_exclude_export_memory(self):
        _,mid=self.remember()
        await self.service.handle(self.event(f'/memory exclude {mid}'))
        self.assertNotIn('Mi chiamo Alice',json.dumps(personal_bundle(self.store,2)))

    async def test_40_admin_permission_denied(self):
        result=await self.service.handle(self.event('/admin users'))
        self.assertIn('Permessi amministratore',result.text)

    async def test_41_admin_test_key_synthetic_only(self):
        self.remember('Mi chiamo SEGRETO_ALICE')
        key=self.keys.issue(1,2,'test')
        result=await self.service.handle(self.event('/admin export 2 '+key,uid=1))
        self.assertTrue(json.loads(result.document)['test_only'])
        self.assertNotIn('SEGRETO',result.document.decode())

    async def test_42_admin_export_requires_owner_delegation(self):
        result=await self.service.handle(self.event('/admin export 2 '+self.keys.issue(2,2),uid=1))
        self.assertIn('Chiave non valida',result.text)

    async def test_43_admin_authorized_delegation_works(self):
        self.remember()
        key=self.keys.issue(2,2,'delegate')
        result=await self.service.handle(self.event('/admin export 2 '+key,uid=1))
        self.assertIn('Mi chiamo Alice',result.document.decode())

    async def test_44_admin_audit_has_no_token(self):
        key=self.keys.issue(1,2,'test')
        await self.service.handle(self.event('/admin export 2 '+key,uid=1))
        audit=json.dumps(self.store.rows('SELECT * FROM audit_logs'))
        self.assertIn('admin_export',audit);self.assertNotIn(key,audit)

    async def test_45_backup_nonadmin_denied(self):
        result=await self.service.handle(self.event('/backup'))
        self.assertIn('Solo l’amministratore',result.text)
        self.assertIsNone(result.document)

    def test_46_backup_encrypted_restore(self):
        self.remember('Mi chiamo SEGRETO_ALICE')
        path=self.backups.create()
        self.assertNotIn(b'SEGRETO_ALICE',path.read_bytes())
        target=self.settings.data/'restored.sqlite3'
        self.backups.restore(path,target)
        restored=Store(target)
        self.assertEqual(restored.profile(2)[0]['content'],'Mi chiamo SEGRETO_ALICE')
        restored.close()

    def test_47_backup_tampering_fails(self):
        path=self.backups.create();data=bytearray(path.read_bytes());data[50]^=1;path.write_bytes(data)
        with self.assertRaises(Exception):self.backups.restore(path,self.settings.data/'restored.sqlite3')

    def test_48_restore_revokes_tokens_and_sessions(self):
        key=self.keys.issue(2,2)
        self.keys.session(self.keys.issue(2,2,'web'))
        path=self.backups.create();target=self.settings.data/'restored.sqlite3';self.backups.restore(path,target)
        restored=Store(target)
        self.assertEqual(restored.rows('SELECT * FROM web_sessions'),[])
        self.assertTrue(restored.rows('SELECT * FROM export_keys')[0]['revoked'])
        restored.close()

    def test_49_backup_retention_and_schedules(self):
        self.settings.daily_retention=2
        for i in range(5):self.backups.create('daily')
        self.assertEqual(len(list(self.backups.root.glob('daily_*'))),2)
        self.backups.scheduled(datetime(2026,9,1,tzinfo=timezone.utc))
        self.assertEqual(len(list(self.backups.root.glob('weekly_*'))),1)
        self.assertEqual(len(list(self.backups.root.glob('monthly_*'))),1)

    async def test_50_deletion_private_and_group_sources(self):
        self.remember();self.remember('Mi chiamo Alice pubblica',group=-10);self.remember('Mi chiamo Bob',uid=3)
        await self.service.handle(self.event('/forget all confermo'))
        self.assertEqual(self.store.profile(2),[])
        self.assertEqual(self.store.recent(Scope('user',2)),[])
        self.assertEqual(self.store.memories(Scope('group',-10)),[])
        self.assertTrue(self.store.profile(3))

    async def test_51_delete_memory_removes_source(self):
        _,mid=self.remember()
        await self.service.handle(self.event('/forget '+str(mid)))
        self.assertEqual(self.store.recent(Scope('user',2)),[])

    async def test_52_cannot_delete_other_user_memory(self):
        _,mid=self.remember('Mi chiamo Bob',uid=3)
        result=await self.service.handle(self.event('/forget '+str(mid)))
        self.assertIn('non trovata',result.text);self.assertTrue(self.store.profile(3))

    async def test_53_deletion_removes_previous_backups(self):
        self.remember();old=self.backups.create('weekly')
        await self.service.handle(self.event('/forget all confermo'))
        self.assertFalse(old.exists())

    def test_54_telegram_mention_and_utf16_emoji(self):
        message={'from':{'id':2,'first_name':'Alice'},'chat':{'id':-10,'type':'group'},
                 'message_id':1,'text':'😀 @AlbaBot ciao','entities':[{'type':'mention','offset':3,'length':8}]}
        event=normalize(message,{'id':100,'username':'AlbaBot'})
        self.assertTrue(event.mention_bot)

    def test_55_reply_to_bot(self):
        message={'from':{'id':2},'chat':{'id':-10,'type':'group'},'message_id':2,'text':'ciao',
                 'reply_to_message':{'message_id':1,'from':{'id':100}}}
        event=normalize(message,{'id':100,'username':'AlbaBot'})
        self.assertTrue(event.reply_to_bot);self.assertEqual(event.reply_id,1)

    def test_56_other_bot_command_ignored(self):
        message={'from':{'id':2},'chat':{'id':2,'type':'private'},'message_id':1,'text':'/help@otherbot'}
        self.assertIsNone(normalize(message,{'id':100,'username':'AlbaBot'}))

    def test_57_bot_message_ignored(self):
        message={'from':{'id':2,'is_bot':True},'chat':{'id':2,'type':'private'},'message_id':1,'text':'ciao'}
        self.assertIsNone(normalize(message,{'id':100,'username':'AlbaBot'}))

    async def test_58_group_silent_default_but_stored(self):
        result=await self.service.handle(self.event('Oggi parliamo di un evento',group=-10))
        self.assertEqual(result.text,'');self.assertEqual(len(self.store.recent(Scope('group',-10))),1)

    async def test_59_group_mention_answers(self):
        result=await self.service.handle(self.event('@AlbaBot ciao',group=-10,mention_bot=True))
        self.assertTrue(result.text)

    async def test_60_group_auto_configurable(self):
        self.assertFalse(self.service.should_reply(self.event('Una domanda sufficientemente lunga per tutti?',group=-10)))
        await self.service.handle(self.event('/group auto on',uid=1,group=-10))
        self.assertTrue(self.service.should_reply(self.event('Una domanda sufficientemente lunga per tutti?',group=-10)))

    async def test_61_group_config_requires_telegram_admin(self):
        async def no(*args):return False
        self.service.group_admin_check=no
        result=await self.service.handle(self.event('/group off',uid=1,group=-10))
        self.assertIn('amministratore Telegram',result.text)

    async def test_62_private_permission_checks_chat_owner(self):
        e=self.event('/export_key');e.chat_id=3
        result=await self.service.handle(e)
        self.assertIn('chat privata',result.text)

    async def test_63_idempotent_telegram_delivery(self):
        e=self.event('Ciao',message_id=7)
        await self.service.handle(e);result=await self.service.handle(e)
        self.assertEqual(result.text,'')
        self.assertEqual(len(self.store.recent(Scope('user',2))),2)

    async def test_64_stats_fields(self):
        result=await self.service.handle(self.event('/stats'))
        for field in ('RAM','CPU','DISK','DATABASE SIZE','MODEL','MESSAGES','MEMORIES','RESPONSE TIME'):
            self.assertIn(field,result.text)

    def test_65_persona_export_has_required_parts(self):
        self.remember();persona=generate_persona(personal_bundle(self.store,2))
        for key in ('system_prompt','personality','initial_memory','behavioral_instructions','conversation_examples'):
            self.assertIn(key,persona)

    async def test_66_web_session_revocation(self):
        session,csrf=self.keys.session(self.keys.issue(2,2,'web'))
        self.assertEqual(self.keys.identify(session)['user_id'],2)
        self.keys.revoke(2,2)
        with self.assertRaises(PermissionError):self.keys.identify(session)

    async def test_67_keys_not_available_via_web_command(self):
        e=self.event('/export_key');e.transport='web'
        result=await self.service.handle(e)
        self.assertIn('Telegram',result.text)

    async def test_68_http_unauthenticated_denied(self):
        client=TestClient(TestServer(web_app(self.service)))
        await client.start_server()
        try:self.assertEqual((await client.get('/api/history')).status,403)
        finally:await client.close()

    async def test_69_http_user_isolation_and_csrf(self):
        self.remember();self.remember('Mi chiamo SEGRETO_BOB',uid=3)
        session,csrf=self.keys.session(self.keys.issue(2,2,'web'))
        client=TestClient(TestServer(web_app(self.service)))
        await client.start_server()
        headers={'Cookie':'session='+session}
        try:
            response=await client.get('/api/history',headers=headers)
            self.assertNotIn('SEGRETO_BOB',await response.text())
            response=await client.post('/api/chat',json={'message':'ciao'},headers=headers)
            self.assertEqual(response.status,403)
            headers['X-CSRF-Token']=csrf
            response=await client.post('/api/chat',json={'message':'ciao','user_id':3},headers=headers)
            self.assertEqual(response.status,403)
        finally:await client.close()

    async def test_70_http_login_cookie_secure(self):
        client=TestClient(TestServer(web_app(self.service)));await client.start_server()
        try:
            response=await client.post('/api/login',json={'token':self.keys.issue(2,2,'web')})
            self.assertEqual(response.status,200)
            cookie=response.headers['Set-Cookie']
            self.assertIn('Secure',cookie);self.assertIn('HttpOnly',cookie);self.assertIn('SameSite=Strict',cookie)
            self.assertEqual(response.headers['Cache-Control'],'no-store')
        finally:await client.close()

    def test_71_admin_flag_cannot_bypass_permissions(self):
        key=self.keys.issue(3,3,'delegate')
        with self.assertRaises(PermissionError):export_document(self.store,self.keys,2,3,key,admin=True)

    def test_72_nonadmin_cannot_issue_test_key(self):
        with self.assertRaises(PermissionError):self.keys.issue(2,3,'test')

    def test_73_silent_personal_hallucination_rejected(self):
        payload={'reply':'Tua moglie si chiama Maria','used_memory_ids':[],'personal_claims':[]}
        self.assertIsNone(validate_response(payload,{'memories':[]}))

    async def test_74_queued_updates_erased(self):
        self.store.execute('CREATE TABLE pending_updates(update_id INTEGER PRIMARY KEY,payload TEXT)')
        self.store.execute('INSERT INTO pending_updates VALUES(?,?)',(1,json.dumps({'uid':2,'text':'SEGRETO'})))
        await self.service.handle(self.event('/forget all confermo'))
        self.assertEqual(self.store.rows('SELECT * FROM pending_updates'),[])

    def test_75_memory_has_intermediate_summary(self):
        mid,mem=self.remember()
        memory=self.store.rows('SELECT * FROM memories WHERE id=?',(mem,))[0]
        summary=self.store.rows('SELECT * FROM summaries WHERE id=?',(memory['summary_id'],))[0]
        self.assertIn(mid,json.loads(summary['source_ids']))
        self.assertEqual(summary['scope'],memory['scope'])

    async def test_76_tone_adapts_only_in_private(self):
        before=self.store.tone(2)['verbosity']
        await self.service.handle(self.event('Preferisco risposte brevi',group=-10,mention_bot=True))
        self.assertEqual(self.store.tone(2)['verbosity'],before)
        await self.service.handle(self.event('Preferisco risposte brevi'))
        self.assertEqual(self.store.tone(2)['verbosity'],before-.04)

    async def test_77_web_jobs_bound_to_owner(self):
        session,csrf=self.keys.session(self.keys.issue(2,2,'web'))
        bob,bob_csrf=self.keys.session(self.keys.issue(3,3,'web'))
        client=TestClient(TestServer(web_app(self.service)));await client.start_server()
        try:
            headers={'Cookie':'session='+session,'X-CSRF-Token':csrf}
            response=await client.post('/api/chat',json={'message':'ciao'},headers=headers)
            self.assertEqual(response.status,202)
            job=(await response.json())['job_id']
            response=await client.get('/api/jobs/'+job,headers={'Cookie':'session='+bob})
            self.assertEqual(response.status,403)
            await asyncio.sleep(.02)
            response=await client.get('/api/jobs/'+job,headers=headers)
            self.assertIn('reply',await response.json())
        finally:await client.close()

    async def test_78_bootstrap_private_single_use(self):
        self.settings.admins=()
        key='bootstrap-test-secret'
        self.store.set_setting('bootstrap_digest',self.keys.digest(key))
        result=await self.service.handle(self.event('/bootstrap '+key,uid=99,group=-10))
        self.assertIn('chat privata',result.text)
        result=await self.service.handle(self.event('/bootstrap '+key,uid=99))
        self.assertTrue(self.service.is_admin(99))
        result=await self.service.handle(self.event('/bootstrap '+key,uid=3))
        self.assertIn('già configurato',result.text)

    async def test_79_group_self_recall_does_not_attribute_other(self):
        self.remember('Mi chiamo Bob',uid=3,group=-10)
        result=await self.service.handle(self.event('Ti ricordi il mio nome?',group=-10,mention_bot=True))
        self.assertNotIn('Mi chiamo Bob',result.text)

    def test_80_group_memory_authors_kept(self):
        self.remember('Mi chiamo Bob',uid=3,group=-10)
        context=build_context(self.store,Scope('group',-10),'nome')
        self.assertEqual(context['memories'][0]['authors'],[3])

    async def test_81_report_recurring_observations(self):
        self.store.add_message(Scope('user',2),2,'user','Sono stressato per il lavoro')
        self.store.add_message(Scope('user',2),2,'user','Il lavoro mi porta stress')
        result=await self.service.handle(self.event('Voglio una diagnosi'))
        self.assertIn('lavoro: citato in 2 messaggi',result.text)

    async def test_82_group_report_only_current_author(self):
        self.store.add_message(Scope('group',-10),3,'user','Sono triste SEGRETO_BOB')
        result=await self.service.handle(self.event('Voglio una diagnosi',group=-10,mention_bot=True))
        self.assertNotIn('SEGRETO_BOB',result.text)


if __name__=='__main__':unittest.main()
