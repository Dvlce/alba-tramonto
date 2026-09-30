import time
import unittest
from unittest.mock import AsyncMock,patch
import test_tramonto as fixtures
from identity import Identity

class IdentityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await fixtures.TramontoTests.asyncSetUp(self)
        self.store.set_setting('automatic_web_access','1')
    asyncTearDown=fixtures.TramontoTests.asyncTearDown;req=fixtures.TramontoTests.req
    @property
    def manager(self):return self.service.identity
    def configure(self,provider='google'):
        self.manager.save_config(provider,{'client_id':'AC'+'1'*32 if provider=='phone' else 'client-test','client_secret':'private-test-secret','service_sid':'VA'+'2'*32,'enabled':True})
    async def auth_headers(self):
        response=await self.client.get('/auth/providers');body=await response.json()
        return {'Cookie':'auth_csrf='+response.cookies['auth_csrf'].value,'X-CSRF-Token':body['csrf']}
    def profile(self,subject='123',email='verified@example.invalid'):return {'subject':subject,'name':'Persona test','email':email}
    def target(self,uid=1):return {'uid':uid,'session_digest':self.keys.identify(self.headers[uid]['Cookie'].split('=',1)[1])['digest']}
    async def test_01_disabled_by_default(self):
        response=await self.client.get('/auth/providers');data=await response.json();self.assertFalse(any(p['enabled'] for p in data['providers']));self.assertFalse(data['phone_enabled'])
    async def test_02_config_admin_only(self):
        self.assertEqual((await self.req('/api/admin/identity',raw=True,uid=2)).status,403)
    async def test_03_secrets_encrypted_and_masked(self):
        self.configure();rows=self.store.rows('SELECT payload FROM identity_settings');self.assertNotIn(b'private-test-secret',rows[0]['payload']);data=await(await self.req('/api/admin/identity',raw=True)).json();self.assertTrue(data['providers'][0]['has_secret']);self.assertNotIn('private-test-secret',str(data))
    async def test_04_empty_secret_keeps_previous(self):
        self.configure();self.manager.save_config('google',{'client_secret':'','enabled':False});self.assertEqual(self.manager.config('google')['client_secret'],'private-test-secret');self.assertFalse(self.manager.configured('google'))
    async def test_05_cannot_enable_without_secret(self):
        with self.assertRaises(ValueError):self.manager.save_config('github',{'client_id':'id','enabled':True})
    async def test_06_csrf_required(self):
        self.configure();self.assertEqual((await self.client.post('/auth/google/start',json={'privacy_accepted':True})).status,403)
    async def test_07_consent_required(self):
        self.configure();headers=await self.auth_headers();self.assertEqual((await self.client.post('/auth/google/start',json={'privacy_accepted':False},headers=headers)).status,403)
    async def test_08_google_pkce_and_state(self):
        self.configure();headers=await self.auth_headers();response=await self.client.post('/auth/google/start',json={'privacy_accepted':True},headers=headers);self.assertEqual(response.status,200);data=await response.json();self.assertIn('code_challenge_method=S256',data['url']);self.assertIn('oauth_state',response.cookies)
    async def test_09_flow_replay_rejected(self):
        token=self.manager.flow('google',{'uid':1,'test':'encrypted'});self.manager.read_flow(token,'google',True)
        with self.assertRaises(PermissionError):self.manager.read_flow(token,'google')
    async def test_10_expiry_rejected(self):
        token=self.manager.flow('github',{});self.store.execute('UPDATE auth_flows SET expires=0')
        with self.assertRaises(PermissionError):self.manager.read_flow(token,'github')
    async def test_11_verified_new_identity_stable(self):
        uid=self.manager.assign('google',self.profile(),{});self.assertLess(uid,0);self.assertEqual(self.manager.assign('google',self.profile(),{}),uid);self.assertTrue(self.store.allowed(uid))
    async def test_12_same_email_never_merges(self):
        a=self.manager.assign('google',self.profile(),{});b=self.manager.assign('discord',self.profile(),{});self.assertNotEqual(a,b)
    async def test_13_link_keeps_telegram_uid(self):
        uid=self.manager.assign('google',self.profile(),self.target());self.assertEqual(uid,1);self.assertEqual(self.manager.assign('google',self.profile(),{}),1)
    async def test_14_foreign_link_rejected(self):
        self.manager.assign('google',self.profile(),self.target(1))
        with self.assertRaises(PermissionError):self.manager.assign('google',self.profile(),self.target(2))
    async def test_15_revoked_session_cannot_link(self):
        target=self.target();self.store.execute('DELETE FROM web_sessions WHERE user_id=1')
        with self.assertRaises(PermissionError):self.manager.assign('google',self.profile(),target)
    async def test_16_revoked_user_not_auto_approved(self):
        uid=self.manager.assign('google',self.profile(),{});self.store.execute('UPDATE users SET authorized=0 WHERE id=?',(uid,));self.store.execute('INSERT INTO access_blocks VALUES(?,?)',(uid,time.time()))
        with self.assertRaises(PermissionError):self.manager.assign('google',self.profile(),{})
    async def test_17_capacity_waits_without_duplicate_identity(self):
        object.__setattr__(self.settings,'max_users',4)
        for _ in range(2):
            with self.assertRaises(PermissionError):self.manager.assign('google',self.profile(),{})
        self.assertEqual(len(self.store.rows('SELECT * FROM auth_accounts')),1)
    async def test_18_callback_wrong_state(self):
        self.configure();response=await self.client.get('/auth/google/callback?state=bad&code=test',allow_redirects=False);self.assertEqual(response.status,302);self.assertIn('auth_error',response.headers['Location'])
    async def test_19_callback_verified_login(self):
        self.configure();token=self.manager.flow('google',{'remember':True,'verifier':'test'})
        with patch.object(self.manager,'exchange',AsyncMock(return_value=self.profile())):
            response=await self.client.get('/auth/google/callback?state='+token+'&code=test',headers={'Cookie':'oauth_state='+token},allow_redirects=False)
        self.assertEqual(response.headers['Location'],'/');self.assertIn('session',response.cookies);self.assertTrue(response.cookies['session']['httponly']);self.assertTrue(response.cookies['session']['secure'])
    async def test_20_google_email_verified_required(self):
        self.configure();responses=[{'access_token':'test'},{'sub':'id','email_verified':False}]
        with patch.object(self.manager,'http',AsyncMock(side_effect=responses)),self.assertRaises(PermissionError):await self.manager.exchange('google','code',{'verifier':'test'})
    async def test_21_discord_email_verified_required(self):
        self.configure('discord')
        with patch.object(self.manager,'http',AsyncMock(side_effect=[{'access_token':'test'},{'id':'id','verified':False}])),self.assertRaises(PermissionError):await self.manager.exchange('discord','code',{})
    async def test_22_github_verified_primary_email(self):
        self.configure('github');responses=[{'access_token':'test'},{'id':1,'login':'user'},[{'verified':False,'email':'bad'},{'verified':True,'primary':True,'email':'ok'}]]
        with patch.object(self.manager,'http',AsyncMock(side_effect=responses)):self.assertEqual((await self.manager.exchange('github','code',{}))['email'],'ok')
    async def test_23_phone_credentials_required(self):
        headers=await self.auth_headers();self.assertEqual((await self.client.post('/auth/phone/send',headers=headers,json={'phone':'+391234567890','privacy_accepted':True})).status,403)
    async def test_24_phone_flow_and_rate_limit(self):
        self.configure('phone');headers=await self.auth_headers();value={'phone':'+391234567890','privacy_accepted':True}
        with patch.object(self.manager,'sms',AsyncMock(return_value={'status':'pending'})):
            response=await self.client.post('/auth/phone/send',headers=headers,json=value);self.assertEqual(response.status,200);token=response.cookies['phone_flow'].value;self.assertNotIn(b'+391234567890',self.store.rows('SELECT payload FROM auth_flows')[0]['payload']);self.assertEqual((await self.client.post('/auth/phone/send',headers=headers,json=value)).status,429)
            headers['Cookie']+='; phone_flow='+token
        with patch.object(self.manager,'sms',AsyncMock(return_value={'status':'approved'})):
            response=await self.client.post('/auth/phone/check',headers=headers,json={'code':'123456'});self.assertEqual(response.status,200)
        self.assertNotIn('+391234567890',str(self.store.rows('SELECT * FROM auth_accounts')))
    async def test_25_phone_failed_attempts_capped(self):
        self.configure('phone');headers=await self.auth_headers();token=self.manager.flow('phone',{'phone':'+391234567890','remember':True});headers['Cookie']+='; phone_flow='+token
        with patch.object(self.manager,'sms',AsyncMock(return_value={'status':'pending'})) as mocked:
            for _ in range(6):self.assertEqual((await self.client.post('/auth/phone/check',headers=headers,json={'code':'123456'})).status,403)
        self.assertEqual(mocked.await_count,5)
    async def test_26_accounts_isolation(self):
        self.manager.assign('google',self.profile(),self.target(1));self.assertEqual((await(await self.req('/api/accounts',uid=2,raw=True)).json())['accounts'],[])
    async def test_27_erasure_is_scoped(self):
        self.manager.assign('google',self.profile(),self.target(1));self.manager.assign('github',self.profile(),self.target(2));self.manager.flow('google',self.target(1));self.manager.flow('github',self.target(2));self.store.forget_user(1);self.assertEqual([r['user_id'] for r in self.store.rows('SELECT * FROM auth_accounts')],[2]);self.assertEqual([r['user_id'] for r in self.store.rows('SELECT * FROM auth_flows')],[2])
