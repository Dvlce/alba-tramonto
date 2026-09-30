import asyncio
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from aiohttp.test_utils import TestClient,TestServer
from app import web_app
from backups import Backups
from config import Settings
from engine import Engine
from security import Keys,secret_file
from service import Service
from store import Store

class DeviceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.settings=Settings(root=Path(self.tmp.name),admins=(1,),allowed=(2,3))
        self.store=Store(self.settings.data/'alba.sqlite3'); self.secret=secret_file(self.settings.data/'auth.key'); self.keys=Keys(self.store,self.secret)
        self.service=Service(self.store,self.settings,self.keys,Engine(self.store,self.settings,None),Backups(self.store,self.settings))
        for uid in (1,2,3): self.store.register(uid,str(uid))
        self.cookie,self.csrf=self.keys.create_session(2,True,'Telefono'); self.headers={'Cookie':'session='+self.cookie,'X-CSRF-Token':self.csrf}
        self.client=TestClient(TestServer(web_app(self.service))); await self.client.start_server()
    async def asyncTearDown(self): await self.client.close(); self.store.close(); self.tmp.cleanup()
    async def req(self,body=None,headers=None,path='/api/devices'):
        return await self.client.request('POST' if body is not None else 'GET',path,json=body,headers=headers or self.headers)
    def other(self,uid=2):
        cookie,csrf=self.keys.create_session(uid,True,'Computer'); return cookie,{'Cookie':'session='+cookie,'X-CSRF-Token':csrf}
    def test_01_remembered_ninety_days(self):
        row=self.keys.identify(self.cookie); self.assertEqual(row['remembered'],1); self.assertAlmostEqual(row['expires']-time.time(),90*86400,delta=2)
    def test_02_short_twelve_hours(self):
        cookie,_=self.keys.create_session(2); row=self.keys.identify(cookie); self.assertEqual(row['remembered'],0); self.assertAlmostEqual(row['expires']-time.time(),12*3600,delta=2)
    def test_03_only_digest_stored(self):
        self.assertNotIn(self.cookie,str(self.store.rows('SELECT * FROM web_sessions'))); self.assertNotIn(self.cookie,str(self.store.rows('SELECT * FROM audit_logs')))
    def test_04_daily_renewal_extends_remembered_session(self):
        row=self.keys.identify(self.cookie); future=time.time()+2*86400
        with patch('security.time.time',return_value=future): self.assertTrue(self.keys.renew_session(row['digest']))
        self.assertAlmostEqual(self.keys.identify(self.cookie)['expires'],future+90*86400,delta=1)
    def test_05_short_sessions_do_not_renew(self):
        cookie,_=self.keys.create_session(2); row=self.keys.identify(cookie)
        with patch('security.time.time',return_value=time.time()+3600): self.assertFalse(self.keys.renew_session(row['digest']))
        self.assertEqual(self.keys.identify(cookie)['expires'],row['expires'])
    def test_06_expired_sessions_cannot_be_revived(self):
        row=self.keys.identify(self.cookie); self.store.execute('UPDATE web_sessions SET expires=0 WHERE digest=?',(row['digest'],))
        self.assertFalse(self.keys.renew_session(row['digest']))
        with self.assertRaises(PermissionError): self.keys.identify(self.cookie)
    async def test_07_device_list_is_owner_only_without_secrets(self):
        self.other(); self.other(3); response=await self.req(); data=await response.json(); self.assertEqual(len(data['devices']),2)
        for value in data['devices']:
            for field in ('csrf','digest','user_id','ip','cookie'): self.assertNotIn(field,value)
        self.assertEqual(sum(value['current'] for value in data['devices']),1)
    async def test_08_label_and_remember_opt_out(self):
        response=await self.req({'action':'remember','remember':False,'label':'Portatile'}); self.assertEqual(response.status,200)
        row=self.keys.identify(self.cookie); self.assertEqual(row['label'],'Portatile'); self.assertEqual(row['remembered'],0); self.assertEqual(int(response.cookies['session']['max-age']),43200)
    async def test_09_other_owner_cannot_revoke_device(self):
        cookie,headers=self.other(3); foreign=self.keys.identify(cookie)['device_id']
        self.assertEqual((await self.req({'action':'revoke','device_id':foreign})).status,403); self.keys.identify(cookie)
    async def test_10_revoke_other_device_preserves_current(self):
        cookie,_=self.other(); device=self.keys.identify(cookie)['device_id']; self.assertEqual((await self.req({'action':'revoke','device_id':device})).status,200)
        with self.assertRaises(PermissionError): self.keys.identify(cookie)
        self.keys.identify(self.cookie)
    async def test_11_revoke_others_preserves_other_owners(self):
        cookie,_=self.other(); bob,_=self.other(3); await self.req({'action':'revoke_others'})
        with self.assertRaises(PermissionError): self.keys.identify(cookie)
        self.keys.identify(self.cookie); self.keys.identify(bob)
    async def test_12_revoke_current_and_expired_error_code(self):
        device=self.keys.identify(self.cookie)['device_id']; response=await self.req({'action':'revoke','device_id':device})
        self.assertTrue((await response.json())['current_revoked']); self.assertEqual(response.cookies['session']['max-age'],'0')
        response=await self.req(); self.assertEqual((await response.json())['code'],'auth_expired')
    async def test_13_csrf_and_owner_forgery_rejected(self):
        response=await self.req({'action':'revoke_others'},headers={'Cookie':'session='+self.cookie}); self.assertEqual(response.status,403)
        for field in ('user_id','digest','scope'):
            self.assertEqual((await self.req({'action':'revoke_others',field:3})).status,403)
        self.assertEqual((await self.req(path='/api/devices?user_id=3')).status,403)
    async def test_14_login_sets_secure_persistent_cookie(self):
        username,password=self.keys.set_web_password(2,2)
        response=await self.client.post('/api/login',json={'username':username,'password':password,'remember':True},headers={'User-Agent':'Mozilla/5.0 (iPhone) Safari/1'})
        self.assertEqual(response.status,200); cookie=response.cookies['session']; self.assertTrue(cookie['secure']); self.assertTrue(cookie['httponly']); self.assertEqual(cookie['samesite'],'Strict'); self.assertEqual(int(cookie['max-age']),90*86400)
        self.assertEqual(self.keys.identify(cookie.value)['label'],'Safari · iPhone')
    async def test_15_logout_only_revokes_current_browser(self):
        other,_=self.other(); await self.req({},path='/api/logout')
        with self.assertRaises(PermissionError): self.keys.identify(self.cookie)
        self.keys.identify(other)
    def test_16_password_rotation_and_global_revoke(self):
        self.other(); self.keys.set_web_password(2,2)
        self.assertEqual(self.store.rows('SELECT * FROM web_sessions WHERE user_id=2'),[])
    def test_17_sessions_survive_process_restart(self):
        keys=Keys(self.store,self.secret); self.assertEqual(keys.identify(self.cookie)['user_id'],2)
    def test_18_legacy_session_schema_migrates(self):
        path=self.settings.data/'legacy.sqlite3'; db=sqlite3.connect(path)
        db.execute('CREATE TABLE web_sessions(digest TEXT PRIMARY KEY,user_id INTEGER,csrf TEXT,expires REAL)'); db.execute('INSERT INTO web_sessions VALUES(?,?,?,?)',('hash',2,'csrf',time.time()+100)); db.commit(); db.close()
        migrated=Store(path)
        try:
            row=migrated.rows('SELECT * FROM web_sessions')[0]; self.assertTrue(row['device_id']); self.assertEqual(row['remembered'],0); self.assertEqual(row['digest'],'hash')
        finally: migrated.close()
