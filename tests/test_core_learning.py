import io
import asyncio
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock
import test_core
from core.learning import extract_sources, repo_name, LESSONS


class ArchiveTests(unittest.TestCase):
    def archive(self,paths):
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w') as z:
            for name,content in paths.items(): z.writestr(name,content)
        return buf.getvalue()

    def test_public_repo_validation(self):
        self.assertEqual(repo_name('https://github.com/pallets/flask.git'),'pallets/flask')
        for value in ('http://127.0.0.1/x','a/../../b','a/b; id','https://evil.test/a/b','../b'):
            with self.assertRaises(ValueError): repo_name(value)

    def test_archive_traversal_and_secrets(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError): extract_sources(self.archive({'repo/../../escape.py':'x'}),Path(folder))
            result=extract_sources(self.archive({'repo/.env':'SECRET=x','repo/a.py':'print(1)','repo/bin.exe':'binary'}),Path(folder))
            self.assertEqual([r['path'] for r in result],['a.py'])
            self.assertFalse((Path(folder)/'.env').exists())


class LearningTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_core.CoreTests.asyncSetUp
    asyncTearDown = test_core.CoreTests.asyncTearDown

    async def test_coding_routes_to_local_coder(self):
        await self.core.work('chat','Scrivi una funzione Python.')
        self.assertEqual(self.core.error,'')
        payload=next(p for url,p in self.model.calls if url.endswith('/api/chat'))
        self.assertEqual(payload['model'],'qwen2.5-coder:3b')

    async def test_incomplete_stream_is_not_saved_as_answer(self):
        class Broken(test_core.Response):
            def __aiter__(self):
                async def lines(): yield b'{"message":{"content":"Risposta parziale"}}\n'
                return lines()
        self.model.post=lambda *a,**k: Broken({})
        await self.core.work('chat','Ciao')
        self.assertTrue(self.core.error)
        self.assertEqual(self.store.rows("SELECT * FROM core_events WHERE role='assistant'"),[])
        self.assertEqual(self.core.partial,'')
        self.assertEqual(self.core.snapshot()['tokens'][0]['unknown'],1)

    async def test_chat_interrupts_background_study(self):
        began=asyncio.Event()
        async def studying(): began.set();await asyncio.Event().wait()
        self.core.learning.study=studying
        self.core.start('study');await began.wait()
        self.core.start('chat','Parliamo dei telescopi.')
        await self.core.task
        self.assertFalse(self.core.running)
        self.assertTrue(self.store.rows("SELECT * FROM core_events WHERE role='assistant'"))

    async def test_diary_verified_and_failed_with_sources(self):
        lab=self.core.learning
        self.core.configure({'web_enabled':False})
        self.core.lesson_generate=AsyncMock(return_value={'summary':'Conta parole con un dizionario.','code':'def count_words(text): return {}'})
        lab.exercise=AsyncMock(return_value=(1,'AssertionError: output errato'))
        await lab.study()
        entry=lab.diary('Python')[0];self.assertEqual(entry['status'],'failed')
        self.assertIn('AssertionError',entry['result']);self.assertEqual(lab.diary('Sicurezza del codice'),[])
        self.assertEqual(self.core.lesson_generate.await_count,2)
        self.core.lesson_generate=AsyncMock(return_value={'summary':'Query URL.','code':'def parse_query(q): return {}'})
        lab.exercise=AsyncMock(return_value=(0,'PASS: 3 casi indipendenti'))
        await lab.study()
        self.assertEqual(lab.diary()[0]['status'],'verified')
        self.assertEqual(len(self.store.rows("SELECT * FROM core_events WHERE category='diary'")),2)

    async def test_curated_tools_and_arguments(self):
        with self.assertRaises(ValueError): await self.core.learning.install_tool('curl; id')
        lab=self.core.learning;lab.bounded_process=AsyncMock(return_value=(0,'installed'))
        await lab.install_tool('ruff')
        args=lab.bounded_process.await_args.args[0]
        self.assertIn('--only-binary=:all:',args);self.assertIn('ruff==0.16.10',args)
        self.assertEqual(lab.snapshot()['tools'][0]['status'],'ready')

    @unittest.skipUnless(shutil.which('bwrap'),'Linux bubblewrap required')
    async def test_real_sandbox_tests_and_private_isolation(self):
        lab=self.core.learning
        code='from collections import Counter\ndef count_words(text): return dict(Counter(text.lower().split()))'
        rc,out=await lab.exercise(code,LESSONS[0]);self.assertEqual(rc,0,out);self.assertIn('PASS:',out)
        code='from pathlib import Path\nassert not Path("/home").exists()\nassert not Path("/work/../../home").exists()\n'+code
        rc,out=await lab.exercise(code,LESSONS[0]);self.assertEqual(rc,0,out)
        rc,out=await lab.exercise('import socket\nsocket.create_connection(("1.1.1.1",80),timeout=.5)',LESSONS[0]);self.assertNotEqual(rc,0)
        rc,out=await lab.exercise('def count_words(text): return {}',LESSONS[0]);self.assertNotEqual(rc,0)
        with self.assertRaises((TimeoutError,ValueError)): await lab.exercise('while True: print("x"*4000)',LESSONS[0])
