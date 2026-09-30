import time
import unittest
from unittest.mock import AsyncMock
import test_tramonto as fixtures
from service import Incoming
from store import Scope
class MemoryConsent(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=fixtures.TramontoTests.asyncSetUp;asyncTearDown=fixtures.TramontoTests.asyncTearDown;req=fixtures.TramontoTests.req
 async def grant(self,owner=2,admin=1,token=None):
  token=token or self.keys.issue(owner,owner,'memory_read');return await self.req('/api/admin/memory-access','POST',{'user_id':str(owner),'token':token},uid=admin,raw=True)
 async def view(self,owner=2,admin=1):return await self.req('/api/admin/memories?user_id='+str(owner),uid=admin,raw=True)
 async def test_01_admin_needs_owner_consent(self):
  response=await self.view();self.assertEqual(response.status,403);self.assertEqual((await response.json())['code'],'memory_consent_required')
 async def test_02_granted_temporarily(self):
  response=await self.grant();self.assertEqual(response.status,200);self.assertTrue(time.time()<(await response.json())['expires']<time.time()+901);self.assertEqual((await self.view()).status,200)
 async def test_03_other_admin_not_granted(self):
  await self.grant();self.assertEqual((await self.view(admin=4)).status,403)
 async def test_04_key_other_owner_rejected(self):
  token=self.keys.issue(3,3,'memory_read');self.assertEqual((await self.grant(token=token)).status,403)
 async def test_05_export_key_does_not_grant_read(self):
  token=self.keys.issue(2,2,'export');self.assertEqual((await self.grant(token=token)).status,403)
 async def test_06_code_cannot_export(self):
  token=self.keys.issue(2,2,'memory_read')
  with self.assertRaises(PermissionError):self.keys.consume(1,2,token,('delegate',))
 async def test_07_single_use(self):
  token=self.keys.issue(2,2,'memory_read');self.assertEqual((await self.grant(token=token)).status,200);self.assertEqual((await self.grant(token=token)).status,403)
 async def test_08_expiry_blocks_read(self):
  await self.grant();self.store.execute('UPDATE memory_access_grants SET expires=0');self.assertEqual((await self.view()).status,403)
 async def test_09_owner_revokes(self):
  await self.grant();result=await self.service.handle(Incoming(2,'Persona',2,'private','/memory_key revoke'));self.assertIn('revocati',result.text);self.assertEqual((await self.view()).status,403)
 async def test_10_only_owner_can_issue_real_code(self):
  with self.assertRaises(PermissionError):self.keys.issue(1,2,'memory_read')
 async def test_11_nonadmin_cannot_redeem(self):
  self.assertEqual((await self.grant(admin=3)).status,403)
 async def test_12_private_command_only(self):
  result=await self.service.handle(Incoming(2,'Persona',2,'private','/memory_key'));self.assertIn('Codice temporaneo',result.text);self.assertTrue(self.store.rows("SELECT * FROM export_keys WHERE purpose='memory_read'"));before=len(self.store.rows('SELECT * FROM export_keys'));await self.service.handle(Incoming(2,'Persona',-10,'group','/memory_key',mention_bot=True));self.assertEqual(len(self.store.rows('SELECT * FROM export_keys')),before)
 async def test_13_audit_has_no_token(self):
  token=self.keys.issue(2,2,'memory_read');await self.grant(token=token);await self.view();self.assertNotIn(token,str(self.store.rows('SELECT * FROM audit_logs')))
 async def test_14_revocation_of_user_removes_grants(self):
  await self.grant();self.keys.revoke(1,2);self.assertEqual((await self.view()).status,403)
 async def test_15_request_only_after_admin_action(self):
  self.service.request_memory_access=AsyncMock();self.assertEqual(self.service.request_memory_access.await_count,0);response=await self.req('/api/admin/memory-access','POST',{'user_id':'2','action':'request'},raw=True);self.assertEqual(response.status,200);self.service.request_memory_access.assert_awaited_once_with(2)
 async def test_16_request_rate_limit(self):
  self.service.request_memory_access=AsyncMock();await self.req('/api/admin/memory-access','POST',{'user_id':'2','action':'request'},raw=True);response=await self.req('/api/admin/memory-access','POST',{'user_id':'2','action':'request'},raw=True);self.assertEqual(response.status,429)
 async def test_17_admin_own_memory_available(self):self.assertEqual((await self.view(owner=1)).status,200)
 async def test_18_restore_revokes_memory_grants(self):
  await self.grant();backup=self.backups.create('manual');restored=self.settings.data/'check.sqlite3';self.backups.restore(backup,restored);import sqlite3
  with sqlite3.connect(restored) as db:self.assertEqual(db.execute('SELECT count(*) FROM memory_access_grants').fetchone()[0],0)
