import json
import time
import unittest
from unittest.mock import AsyncMock
import test_core
from core.knowledge import source_request
from core.community_sources import FLAGS, payload, stack_entries, joke_entries
from core.learning import PublicSourceError


def question():
    return {'question_id': 42, 'accepted_answer_id': 73, 'title': 'Python &amp; yield', 'body': '<p>How does yield work?</p>', 'owner': {'user_id': 11, 'display_name': 'Alice'}, 'content_license': 'CC BY-SA 4.0', 'last_activity_date': 100}


def answer():
    return {'answer_id': 73, 'question_id': 42, 'is_accepted': True, 'body': '<p>PYTHON_GENERATOR_EXPLANATION</p><pre>def generator():\n    yield 1</pre>', 'owner': {'user_id': 12, 'display_name': 'Bob'}, 'content_license': 'CC BY-SA 3.0', 'last_activity_date': 200}


def joke(ident=0):
    return {'error': False, 'category': 'Programming', 'type': 'twopart', 'setup': 'Why did the Python developer wait?', 'delivery': 'ORIGINAL_TEST_PUNCHLINE', 'id': ident, 'lang': 'en', 'safe': True, 'flags': dict.fromkeys(FLAGS, False)}


class CommunityParserTests(unittest.TestCase):
    def test_source_validation_and_fixed_categories(self):
        self.assertEqual(source_request({'kind': 'stackoverflow', 'query': 'Python asyncio', 'count': 10})['query'], 'Python asyncio')
        self.assertEqual(source_request({'kind': 'jokes', 'query': 'Pun'})['query'], 'Pun')
        for kind, query, count in [('jokes', 'Dark', 1), ('jokes', 'Programming/../../', 1), ('stackoverflow', 'https://localhost/', 1), ('stackoverflow', 'a\nb', 1), ('jokes', 'Pun', 11), ('stackoverflow', 'python', True)]:
            with self.assertRaises(ValueError):source_request({'kind': kind, 'query': query, 'count': count})

    def test_stack_attribution_accepted_answer_code_and_dedup(self):
        rows = stack_entries([question(), question()], [answer()])
        self.assertEqual(len(rows), 1)
        text = rows[0]['content']
        for expected in ('Python & yield', 'Alice', 'Bob', 'CC BY-SA 4.0', 'CC BY-SA 3.0', 'https://stackoverflow.com/users/12', 'https://stackoverflow.com/questions/42', 'https://stackoverflow.com/a/73', 'yield 1'):
            self.assertIn(expected, text)
        self.assertIn('PYTHON_GENERATOR_EXPLANATION', text[:700])

    def test_stack_rejects_closed_unaccepted_mismatched_and_invalid_posts(self):
        for key, value in [('closed_date', 1), ('question_id', True), ('accepted_answer_id', 99)]:
            q = question();q[key] = value
            self.assertEqual(stack_entries([q], [answer()]), [])
        for key, value in [('question_id', 99), ('is_accepted', False), ('body', None)]:
            a = answer();a[key] = value
            self.assertEqual(stack_entries([question()], [a]), [])

    def test_parser_strips_scripts_and_never_accepts_upstream_urls(self):
        q = question();q.update(link='https://localhost/', title='<script>evil()</script>Python')
        a = answer();a['owner']['link'] = 'https://localhost/'
        row = stack_entries([q], [a])[0]
        self.assertNotIn('evil()', row['content']);self.assertNotIn('localhost', row['content'])

    def test_joke_zero_id_punchline_and_unique_source(self):
        rows = joke_entries({'error': False, 'jokes': [joke(), joke()]}, 'Programming')
        self.assertEqual(len(rows), 1);self.assertEqual(rows[0]['key'], 'en:0')
        self.assertIn('ORIGINAL_TEST_PUNCHLINE', rows[0]['content'])
        self.assertIn('idRange=0', rows[0]['url'])

    def test_joke_rejects_flagged_unknown_flags_wrong_language_category_and_empty_punchline(self):
        for key, value in [('safe', False), ('flags', {}), ('category', 'Dark'), ('lang', 'de'), ('delivery', ''), ('id', True)]:
            row = joke();row[key] = value
            self.assertEqual(joke_entries(row, 'Programming'), [])
        row = joke();row['flags']['nsfw'] = True
        self.assertEqual(joke_entries(row, 'Programming'), [])

    def test_payload_bounds_malformed_arrays_and_upstream_errors(self):
        for raw in (b'x', b'[]', b'x'*262145):
            with self.assertRaises(ValueError):payload(raw)
        with self.assertRaises(ValueError):joke_entries({'error': True}, 'Programming')


class CommunityTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_core.CoreTests.asyncSetUp
    asyncTearDown = test_core.CoreTests.asyncTearDown
    req = test_core.CoreTests.req

    async def test_stack_live_path_fetches_only_accepted_answers_and_reuses_partial_cache(self):
        api = self.core.learning.public_get = AsyncMock(side_effect=[json.dumps({'items': [question()], 'quota_remaining': 299}).encode(), json.dumps({'items': [answer()], 'quota_remaining': 298}).encode()])
        request = {'kind': 'stackoverflow', 'query': 'python', 'count': 6}
        first = await self.core.knowledge.import_sources(request)
        self.assertEqual(len(first), 1);self.assertEqual(await self.core.knowledge.import_sources(request), first)
        self.assertEqual(api.await_count, 2)
        self.assertEqual(api.await_args_list[1].args[0], 'https://api.stackexchange.com/2.3/answers/73')
        snapshot = self.core.knowledge.snapshot()
        self.assertEqual(snapshot['community']['stackoverflow_quota'], '298')
        self.assertEqual(snapshot['jobs'][0]['total'], 1)
        self.assertIn('PYTHON_GENERATOR_EXPLANATION', self.core.knowledge.retrieve('Python yield')[0]['content'])
        self.assertEqual(self.core.knowledge.training_examples(), [])

    async def test_free_text_uses_encoded_api_params_not_arbitrary_hosts(self):
        api = self.core.learning.public_get = AsyncMock(side_effect=[json.dumps({'items': [question()]}).encode(), json.dumps({'items': [answer()]}).encode()])
        await self.core.knowledge.import_sources({'kind': 'stackoverflow', 'query': 'Python asyncio'})
        self.assertEqual(api.await_args_list[0].args[0], 'https://api.stackexchange.com/2.3/search/advanced')
        self.assertEqual(api.await_args_list[0].kwargs['params']['q'], 'Python asyncio')

    async def test_quota_exhaustion_stops_second_call_and_honors_backoff(self):
        api = self.core.learning.public_get = AsyncMock(return_value=json.dumps({'items': [question()], 'quota_remaining': 0, 'backoff': 123}).encode())
        self.assertEqual(await self.core.knowledge.import_sources({'kind': 'stackoverflow', 'query': 'python'}), [])
        self.assertEqual(api.await_count, 1)
        self.assertGreater(float(self.store.setting('core_source_retry_stackoverflow')), time.time()+86000)
        self.assertEqual(self.core.knowledge.snapshot()['jobs'][0]['status'], 'error')

    async def test_backoff_shared_between_queries_and_http_error_does_not_block_jokes(self):
        api = self.core.learning.public_get = AsyncMock(side_effect=PublicSourceError('quota', 429, 1200))
        self.assertEqual(await self.core.knowledge.import_sources({'kind': 'stackoverflow', 'query': 'python'}), [])
        self.assertGreater(float(self.store.setting('core_source_retry_stackoverflow')), time.time()+1190)
        self.assertEqual(await self.core.knowledge.import_sources({'kind': 'stackoverflow', 'query': 'javascript'}), [])
        self.assertEqual(api.await_count, 1)
        api.side_effect = None;api.return_value = json.dumps(joke()).encode()
        self.assertEqual(len(await self.core.knowledge.import_sources({'kind': 'jokes', 'query': 'Programming'})), 1)

    async def test_joke_chat_payload_contains_punchline_provenance_and_originality(self):
        api = self.core.learning.public_get = AsyncMock(return_value=json.dumps(joke()).encode())
        await self.core.knowledge.import_sources({'kind': 'jokes', 'query': 'Programming'})
        self.assertIn('safe-mode', api.await_args.kwargs['params'])
        await self.core.work('chat', 'Raccontami una battuta su Python')
        context = json.dumps(next(p for url,p in self.model.calls if url.endswith('/api/chat'))['messages'], ensure_ascii=False)
        for expected in ('ORIGINAL_TEST_PUNCHLINE', 'v2.jokeapi.dev', 'battuta originale'):
            self.assertIn(expected, context)
        self.assertEqual(self.core.knowledge.training_examples(), [])
        self.core.configure({'connectors': {'jokes': False}})
        self.assertEqual(self.core.knowledge.retrieve('battuta'), [])

    async def test_admin_csrf_and_connector_permissions(self):
        value = {'kind': 'jokes', 'query': 'Programming'}
        self.assertEqual((await self.req('/api/notte/sources', 'POST', value, uid=2)).status, 403)
        response = await self.client.post('/api/notte/sources', json=value, headers={'Cookie': self.headers[1]['Cookie']})
        self.assertEqual(response.status, 403)
        self.core.configure({'connectors': {'jokes': False}})
        self.assertEqual((await self.req('/api/notte/sources', 'POST', value)).status, 400)
        self.assertEqual(self.core.knowledge.snapshot()['jobs'], [])

    async def test_expiry_prunes_chunks_events_but_keeps_teacher(self):
        ident,_ = self.core.knowledge.remember('jokes', 'old', 'humor', 'A test joke')
        teacher = self.core.knowledge.teach({'title': 'lesson', 'text': 'Useful lesson'})
        event = self.store.rows('SELECT event_id FROM core_knowledge WHERE id=?', (ident,))[0]['event_id']
        self.store.execute('UPDATE core_knowledge SET updated=? WHERE id=?', (time.time()-31*86400, ident))
        self.core.knowledge.snapshot()
        self.assertFalse(self.store.rows('SELECT * FROM core_events WHERE id=?', (event,)))
        self.assertFalse(self.store.rows('SELECT * FROM core_chunks WHERE event_id=?', (event,)))
        self.assertTrue(self.store.rows('SELECT * FROM core_knowledge WHERE id=?', (teacher['id'],)))

    async def test_autonomy_rotates_and_respects_disabled_connectors_and_due_time(self):
        api = self.core.learning.public_get = AsyncMock(return_value=json.dumps(joke()).encode())
        self.core.configure({'connectors': {'stackoverflow': False}})
        self.assertTrue(self.core.knowledge.community.due())
        await self.core.knowledge.community.study()
        self.assertIn('joke/Programming', api.await_args.args[0])
        self.assertFalse(self.core.knowledge.community.due())
        self.store.set_setting('core_community_last', '0')
        self.core.configure({'study_enabled': False})
        self.assertFalse(self.core.knowledge.community.due())

    async def test_busy_manual_import_suppresses_background_reads(self):
        self.core.knowledge.importing = True
        self.assertFalse(self.core.knowledge.community.due())
        self.core.knowledge.importing = False

    async def test_failed_background_source_is_visible_without_global_retry(self):
        self.core.learning.public_get = AsyncMock(side_effect=PublicSourceError('source unavailable', 403, 600))
        await self.core.work('community')
        self.assertIn('source unavailable', self.core.error)
        self.assertEqual(self.core.failures, 0)
        self.assertEqual(self.core.retry_after, 0)
        self.assertEqual(self.core.knowledge.snapshot()['jobs'][0]['status'], 'error')
