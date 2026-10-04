import asyncio
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiohttp.test_utils import TestClient, TestServer
from app import web_app
from backups import Backups
from config import Settings
from engine import Engine
from security import Keys, secret_file
from service import Service
from store import Store
from core.test_lab import TestLab, validate
from core.optimization_project import project_data

ROOT = Path(__file__).resolve().parents[1]
SHA = 'a' * 64
CONFIG = dict(model='qwen2.5-coder:7b', prompt='17+25?', mode='compare',
              policy='mapped', context=512, output=16)


class Response:
    status = 200
    def __init__(self, body=None, lines=()):
        self.body, self.lines, self.content = body, lines, self
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def json(self): return self.body
    def __aiter__(self):
        async def iterate():
            for line in self.lines: yield line
        return iterate()


class Session:
    def __init__(self): self.calls = []; self.normal = []
    def post(self, url, json=None, **kwargs):
        self.calls.append((url, json))
        if url.endswith('/api/show'): return Response({'modelfile': 'FROM /models/sha256-' + SHA + '\n'})
        return Response(lines=self.normal)


class LabTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.root = Path(self.temporary.name)
        self.store = Store(self.root/'lab.sqlite3'); self.session = Session(); self.token_counts = []
        self.ssd = SimpleNamespace(stop=AsyncMock(), unload_ollama=AsyncMock(), start=AsyncMock(),
            template=AsyncMock(return_value='native template'), planning=lambda *args: {},
            catalog=lambda: {CONFIG['model']: {'sha256': SHA}}, headers={}, failure='', peak={})
        self.core = SimpleNamespace(store=self.store, config={'profile': 'fast'}, ssd=self.ssd,
            settings=SimpleNamespace(llm_url='http://localhost:11434'), engine=SimpleNamespace(session=self.session),
            inference=SimpleNamespace(models=AsyncMock(return_value=[{'name': CONFIG['model'], 'size': 4096}])),
            resources=lambda: {'cpu_percent': 15}, event=lambda *args: None,
            tokens=lambda *args: self.token_counts.append(args))
        self.lab = TestLab(self.core)
    async def asyncTearDown(self): self.store.close(); self.temporary.cleanup()

    def test_bounds_reject_boolean_context_shell_paths_and_silent_truncation(self):
        for change in ({'context': True}, {'output': 500}, {'model': '../model'}, {'mode': 'magic'},
                       {'policy': 'drop_layers'}, {'prompt': 'x'*2001}, {'unknown': 1},
                       {'prompt': 'x'*1800, 'context': 512}):
            with self.subTest(change=change), self.assertRaises(ValueError): validate({**CONFIG, **change})

    async def test_comparison_preserves_profile_and_records_real_regression(self):
        async def sample(config, backend, output):
            output.update(backend=backend, status='ok', content='42', tokens_per_second=4 if backend=='normal' else 2)
        self.lab.sample = sample
        await self.lab.run(CONFIG)
        row = self.lab.snapshot()['runs'][0]
        self.assertEqual(row['result']['decode_change_percent'], -50)
        self.assertTrue(row['result']['same_text']); self.assertIsNone(row['result']['same_tokens'])
        self.assertEqual(self.core.config, {'profile': 'fast'}); self.assertIsNone(self.lab.active)
        self.assertEqual(self.store.rows("SELECT name FROM sqlite_master WHERE name='core_events'"), [])

    async def test_changed_weight_identity_rejects_before_any_model_execution(self):
        self.lab.identity = AsyncMock(return_value='b'*64); self.lab.sample = AsyncMock()
        with self.assertRaises(ValueError): await self.lab.run(CONFIG)
        self.lab.sample.assert_not_awaited(); self.assertEqual(self.lab.snapshot()['runs'], [])

    async def test_partial_output_and_interrupted_run_survive_cancellation(self):
        async def sample(config, backend, output):
            output.update(backend=backend, content='partial real output'); raise asyncio.CancelledError()
        self.lab.sample = sample
        with self.assertRaises(asyncio.CancelledError): await self.lab.run(CONFIG)
        row = self.lab.snapshot()['runs'][0]
        self.assertEqual(row['status'], 'interrupted'); self.assertEqual(row['result']['samples'][0]['content'], 'partial real output')
        self.ssd.stop.assert_awaited(); self.assertIsNone(self.lab.active)

    async def test_one_backend_failure_is_kept_and_does_not_replace_target(self):
        async def sample(config, backend, output):
            output.update(backend=backend, model=config['model'], status='ok', content='42')
            if backend=='optimized': raise ValueError('memory limit')
        self.lab.sample = sample; await self.lab.run(CONFIG)
        row = self.lab.snapshot()['runs'][0]
        self.assertEqual(row['status'], 'error'); self.assertEqual(row['result']['samples'][1]['error'], 'memory limit')
        self.assertTrue(all(s['model']==CONFIG['model'] for s in row['result']['samples']))

    async def test_dense_oversize_normal_is_refused_without_loading(self):
        self.core.inference.models.return_value = [{'name': CONFIG['model'], 'size': 9*1024**3}]
        self.lab.sample = AsyncMock()
        with self.assertRaises(ValueError): await self.lab.run(CONFIG)
        self.lab.sample.assert_not_awaited()

    async def test_ollama_stream_records_declared_counts_and_never_changes_weights(self):
        self.session.normal = [(json.dumps(p)+'\n').encode() for p in (
            {'message': {'content': '42'}}, {'done': True, 'prompt_eval_count': 10, 'eval_count': 2, 'eval_duration': 1000000000})]
        output = {}; await self.lab.sample(CONFIG, 'normal', output)
        self.assertEqual(output['content'], '42'); self.assertEqual(output['tokens_per_second'], 2)
        self.assertEqual(self.token_counts[0], ('benchmark', 10, 2))
        request = self.session.calls[-1][1]; self.assertEqual(request['model'], CONFIG['model']); self.assertNotIn('use_mmap', request['options'])

    async def test_native_stream_is_isolated_from_chat_checkpoint(self):
        parts = [{'content': '42', 'tokens': [19], 'stop': False},
                 {'content': '', 'stop': True, 'timings': {'prompt_n': 10, 'predicted_n': 1, 'predicted_per_second': 2}}]
        self.session.normal = [('data: '+json.dumps(p)+'\n').encode() for p in parts]
        output = {}; await self.lab.sample(CONFIG, 'optimized', output)
        self.assertEqual(output['tokens'], [19]); self.assertEqual(output['sha256'], SHA)
        self.assertFalse(self.session.calls[-1][1]['cache_prompt']); self.ssd.start.assert_awaited_once_with(CONFIG['model'], 'mapped', 512)

    def test_restart_marks_abandoned_row_interrupted(self):
        self.store.execute('INSERT INTO core_lab_runs(config,status,result,created) VALUES(?,?,?,?)',
                           (json.dumps(CONFIG), 'running', '{}', 1))
        TestLab(self.core)
        self.assertEqual(self.lab.snapshot()['runs'][0]['status'], 'interrupted')

    def test_public_project_never_reads_private_lab_rows(self):
        self.store.execute('INSERT INTO core_lab_runs(config,status,result,created) VALUES(?,?,?,?)',
                           (json.dumps({**CONFIG, 'prompt': 'private-secret'}), 'ok', '{}', 1))
        self.assertNotIn('private-secret', json.dumps(project_data(self.root)))
        (self.root/'docs').mkdir()
        (self.root/'docs/TEST_LAB_RESULTS.json').write_text(json.dumps({'samples': [{'content': 'public-42'}]}))
        public = project_data(self.root)
        self.assertEqual(public['lab_measurements']['samples'][0]['content'], 'public-42')
        self.assertNotIn('private-secret', json.dumps(public))


class LabWebTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        for name in ('web.html', 'web.css', 'web.js', 'notte.html', 'notte.css', 'notte.js',
                     'optimization.html', 'optimization.css', 'optimization.js'):
            shutil.copy2(ROOT/name, self.root/name)
        self.settings = Settings(root=self.root, admins=(1,), allowed=(2,))
        self.store = Store(self.settings.data/'alba.sqlite3'); self.keys = Keys(self.store, secret_file(self.settings.data/'auth.key'))
        self.service = Service(self.store, self.settings, self.keys, Engine(self.store, self.settings, Session()), Backups(self.store, self.settings))
        for uid in (1, 2): self.store.register(uid, 'Fixture')
        self.client = TestClient(TestServer(web_app(self.service))); await self.client.start_server()
        self.headers = {}
        for uid in (1, 2):
            cookie, csrf = self.keys.create_session(uid, True)
            self.headers[uid] = {'Cookie': 'session='+cookie, 'X-CSRF-Token': csrf}
    async def asyncTearDown(self): await self.client.close(); self.store.close(); self.tmp.cleanup()

    async def test_public_site_and_data_are_available_but_private_runs_are_admin_only(self):
        for path in ('/optimization', '/optimization/data', '/optimization/assets/optimization.js'):
            self.assertEqual((await self.client.get(path)).status, 200)
        self.assertEqual((await self.client.get('/api/notte/lab', headers=self.headers[2])).status, 403)
        self.assertEqual((await self.client.get('/api/notte/lab', headers=self.headers[1])).status, 200)
        self.assertEqual((await self.client.get('/optimization/reports/server.key')).status, 404)
        (self.root/'docs/ssd-results').mkdir(parents=True)
        for name in ('TEST_LAB_RESULTS.md', 'TEST_LAB_RESULTS.json'):
            shutil.copy2(ROOT/'docs'/name, self.root/'docs'/name)
        shutil.copy2(ROOT/'docs/ssd-results/test-lab-comparison.svg', self.root/'docs/ssd-results/test-lab-comparison.svg')
        for name in ('TEST_LAB_RESULTS.md', 'TEST_LAB_RESULTS.json', 'test-lab-comparison.svg'):
            self.assertEqual((await self.client.get('/optimization/reports/'+name)).status, 200)

    async def test_lab_start_requires_csrf_and_rejects_extra_parameters(self):
        without = {'Cookie': self.headers[1]['Cookie']}
        self.assertEqual((await self.client.post('/api/notte/lab', headers=without, json=CONFIG)).status, 403)
        self.assertEqual((await self.client.post('/api/notte/lab', headers=self.headers[1], json={**CONFIG, 'command': 'bad'})).status, 403)

    async def test_private_export_requires_admin_and_preserves_output(self):
        self.store.execute('INSERT INTO core_lab_runs(config,status,result,created) VALUES(?,?,?,?)',
                           (json.dumps(CONFIG), 'interrupted', json.dumps({'content': 'real partial'}), 1))
        self.assertEqual((await self.client.get('/api/notte/lab/1/export', headers=self.headers[2])).status, 403)
        response = await self.client.get('/api/notte/lab/1/export', headers=self.headers[1])
        self.assertEqual(response.status, 200); self.assertEqual((await response.json())['result']['content'], 'real partial')
