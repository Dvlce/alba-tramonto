import asyncio
import html
import json
import time
import unittest
from unittest.mock import AsyncMock, patch
import test_core
from core.knowledge import source_request
from core.reddit import reddit_entries, subreddit_name, RSS_END, RETENTION_SECONDS
from core.generation_policy import plan


def feed(group='learnpython', title='Python functions', text='Use clear names for Python functions.', ident='abc'):
    return ('<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>'+html.escape(title)+
        '</title><updated>2026-10-11T09:00:00Z</updated><link href="https://www.reddit.com/r/'+group+
        '/comments/'+ident+'/example/"/><content type="html">'+html.escape(text)+
        '</content></entry></feed>').encode()


class RedditParserTests(unittest.TestCase):
    def test_python_joke_uses_conversation_budget_but_joke_program_remains_code(self):
        self.assertFalse(plan('Raccontami una battuta sulla programmazione Python')['coding'])
        self.assertEqual(plan('Raccontami una battuta sulla programmazione Python')['output_tokens'],224)
        self.assertTrue(plan('Scrivi una funzione Python per generare battute')['coding'])

    def test_subreddit_names_public_urls_and_limits(self):
        for value in ('LearnPython','r/LearnPython','/r/LearnPython/','https://www.reddit.com/r/LearnPython/'):
            self.assertEqual(subreddit_name(value),'learnpython')
        self.assertEqual(source_request({'kind':'reddit','query':'r/dadjokes','count':12})['query'],'dadjokes')
        for value in ('https://www.reddit.com:443/r/a/', 'https://user@reddit.com/r/a/',
                      'https://reddit.com.evil.test/r/abc/', 'https://reddit.com/r/abc/?token=x',
                      'https://reddit.com/r/abc/#x', 'https://reddit.com/user/name/',
                      'r/a/../../b','r/name/new/.rss', 'https://127.0.0.1/r/abc/', 'a', 'a'*22):
            with self.assertRaises(ValueError):subreddit_name(value)
        for count in (0,13,True,'3'):
            with self.assertRaises(ValueError):source_request({'kind':'reddit','query':'dadjokes','count':count})

    def test_body_preserves_code_lines_drops_author_footer_and_scripts(self):
        rows=reddit_entries(feed(text='<p>A &amp; B</p><pre>def hello():\n    return 1</pre><script>do_evil()</script> submitted by /u/private_name [comments]'))
        self.assertEqual(rows[0]['url'],'https://www.reddit.com/r/learnpython/comments/abc/')
        self.assertIn('A & B',rows[0]['excerpt']);self.assertIn('def hello():\n',rows[0]['excerpt'])
        self.assertNotIn('private_name', rows[0]['excerpt']);self.assertNotIn('do_evil',rows[0]['excerpt'])

    def test_deleted_nsfw_cross_community_and_external_links_not_imported(self):
        self.assertEqual(reddit_entries(feed(text='[removed]')),[])
        self.assertEqual(reddit_entries(feed(title='[deleted]')),[])
        self.assertEqual(reddit_entries(feed(title='NSFW jokes')),[])
        self.assertEqual(reddit_entries(feed('jokes'), 'learnpython'),[])
        for url in ('https://evil.test/r/learnpython/comments/abc/', 'http://reddit.com/r/learnpython/comments/abc/',
                    'https://www.reddit.com:bad/r/learnpython/comments/abc/', 'https://reddit.com/user/someone/'):
            raw=feed().replace(b'https://www.reddit.com/r/learnpython/comments/abc/example/',html.escape(url).encode())
            self.assertEqual(reddit_entries(raw),[])

    def test_duplicate_urls_are_one_post_and_downloads_are_bounded(self):
        raw=feed();entry=raw[raw.index(b'<entry>'):raw.index(b'</entry>')+8]
        repeated=raw.replace(b'</feed>',entry*30+b'</feed>')
        self.assertEqual(len(reddit_entries(repeated)),1)
        for raw in (b'X'*262145,b'<html>Access denied</html>',b'<!DOCTYPE feed><feed/>',b'<!ENTITY x "a"><feed/>'):
            with self.assertRaises(ValueError):reddit_entries(raw)


class RedditKnowledgeTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=test_core.CoreTests.asyncSetUp
    asyncTearDown=test_core.CoreTests.asyncTearDown
    req=test_core.CoreTests.req

    async def test_import_indexes_full_post_with_real_counts_revision_and_link(self):
        self.core.learning.public_get=AsyncMock(return_value=feed(text='Python functions explain variables. '*100))
        imported=await self.core.knowledge.import_sources({'kind':'reddit','query':'learnpython','count':12})
        state=self.core.knowledge.snapshot();source=state['sources'][0]
        self.assertEqual(len(imported),1);self.assertEqual(state['reddit']['documents'],1)
        self.assertGreater(state['reddit']['words'],400);self.assertEqual(state['indexed_percent'],100)
        self.assertEqual(source['revision'],'2026-10-11T09:00:00Z')
        self.assertEqual(state['jobs'][0]['total'],1);self.assertEqual(state['jobs'][0]['completed'],1)
        self.assertEqual(state['jobs'][0]['status'],'ready')
        recalled=await self.core.retrieve('Python functions',prefer_lexical=True)
        self.assertEqual(recalled[0]['category'],'reddit');self.assertEqual(recalled[0]['url'],source['url'])
        self.assertEqual(self.core.knowledge.training_examples(),[])

    async def test_manual_api_requires_admin_and_enabled_connector(self):
        request={'kind':'reddit','query':'dadjokes','count':3}
        self.assertEqual((await self.req('/api/notte/sources','POST',request,uid=2)).status,403)
        self.core.configure({'connectors':{'reddit':False}})
        self.assertEqual((await self.req('/api/notte/sources','POST',request)).status,400)
        self.assertEqual(self.core.knowledge.snapshot()['jobs'],[])

    async def test_humor_is_recalled_from_an_italian_question_and_can_be_disabled(self):
        self.core.learning.public_get=AsyncMock(return_value=feed('dadjokes','An original test pun','A test setup and punchline.'))
        await self.core.knowledge.import_sources({'kind':'reddit','query':'dadjokes'})
        recalled=await self.core.retrieve('Raccontami una battuta divertente',prefer_lexical=True)
        self.assertEqual(recalled[0]['category'],'reddit');self.assertIn('dadjokes',recalled[0]['title'])
        self.core.configure({'connectors':{'reddit':False}})
        self.assertEqual(await self.core.retrieve('battuta',prefer_lexical=True),[])

    async def test_real_chat_payload_receives_punchline_source_and_originality_instruction(self):
        text='A deliberately long test setup. '*12+'END_OF_ORIGINAL_TEST_PUNCHLINE'
        self.core.learning.public_get=AsyncMock(return_value=feed('dadjokes','An original test joke',text))
        await self.core.knowledge.import_sources({'kind':'reddit','query':'dadjokes'})
        await self.core.work('chat','Raccontami una battuta sulla programmazione Python')
        self.assertEqual(self.core.error,'')
        payload=next(p for url,p in self.model.calls if url.endswith('/api/chat'))
        context=json.dumps(payload['messages'],ensure_ascii=False)
        self.assertIn('battuta originale',context);self.assertIn('END_OF_ORIGINAL_TEST_PUNCHLINE',context)
        self.assertIn('https://www.reddit.com/r/dadjokes/comments/abc/',context)
        self.assertEqual(payload['options']['num_predict'],224)

    async def test_short_cache_deduplication_and_changed_post_replace_chunks(self):
        api=self.core.learning.public_get=AsyncMock(return_value=feed(text='The first original explanation.'))
        request={'kind':'reddit','query':'learnpython','count':3}
        first=await self.core.knowledge.import_sources(request)
        second=await self.core.knowledge.import_sources(request)
        self.assertEqual(first,second);self.assertEqual(api.await_count,1)
        self.store.set_setting('core_reddit_read_learnpython',str(time.time()-601))
        api.return_value=feed(text='A revised replacement explanation.')
        self.assertEqual(first,await self.core.knowledge.import_sources(request))
        state=self.core.knowledge.snapshot();self.assertEqual(state['reddit']['documents'],1)
        content=' '.join(r['content'] for r in self.store.rows('SELECT content FROM core_chunks'))
        self.assertIn('revised replacement',content);self.assertNotIn('first original',content)

    async def test_failure_is_visible_and_backoff_prevents_immediate_retry(self):
        api=self.core.learning.public_get=AsyncMock(side_effect=ValueError('HTTP 403'))
        request={'kind':'reddit','query':'webdev','count':3}
        self.assertEqual(await self.core.knowledge.import_sources(request),[])
        self.assertEqual(await self.core.knowledge.import_sources(request),[])
        state=self.core.knowledge.snapshot();self.assertEqual(state['reddit']['documents'],0)
        self.assertEqual(api.await_count,1);self.assertEqual(state['jobs'][0]['status'],'error')
        self.assertIn('10 minuti',state['jobs'][0]['detail']);self.assertGreater(self.core.config['last_reddit'],0)

    async def test_cancel_is_recorded_and_import_can_restart(self):
        begun=asyncio.Event()
        async def delayed(*args,**kwargs):begun.set();await asyncio.Event().wait()
        self.core.learning.public_get=delayed
        self.core.knowledge.start({'kind':'reddit','query':'webdev'})
        await begun.wait();await self.core.knowledge.stop()
        self.assertEqual(self.core.knowledge.snapshot()['jobs'][0]['status'],'interrupted')
        self.assertFalse(self.core.knowledge.importing)

    async def test_expired_cache_removes_retrieval_content_preserves_owner_lessons(self):
        self.core.learning.public_get=AsyncMock(return_value=feed())
        await self.core.knowledge.import_sources({'kind':'reddit','query':'learnpython'})
        self.core.knowledge.teach({'title':'Private lesson','text':'The owner teaches astronomy.'})
        self.store.execute("UPDATE core_knowledge SET updated=? WHERE kind='reddit'",(time.time()-RETENTION_SECONDS-1,))
        state=self.core.knowledge.snapshot();self.assertEqual(state['reddit']['documents'],0)
        self.assertEqual(state['documents'],1);self.assertEqual(self.core.knowledge.retrieve('functions'),[])
        self.assertEqual(self.store.rows("SELECT * FROM core_events WHERE category='reddit' AND role='source'"),[])

    async def test_autonomous_rotation_alternates_programming_and_humor(self):
        api=self.core.learning.public_get=AsyncMock(side_effect=[feed(),feed('dadjokes','A test joke','Original test punchline.')])
        await self.core.learning.reddit();await self.core.learning.reddit()
        self.assertIn('/r/learnpython/',api.await_args_list[0].args[0]);self.assertIn('/r/dadjokes/',api.await_args_list[1].args[0])
        self.assertEqual(self.core.knowledge.snapshot()['reddit']['documents'],2)
        self.assertEqual({r['status'] for r in self.core.learning.diary()},{'read'})
        self.assertEqual(self.core.knowledge.training_examples(),[])

    async def test_announced_rss_sunset_reports_limitation_without_network_calls(self):
        api=self.core.learning.public_get=AsyncMock(return_value=feed())
        with patch('core.knowledge.time.time',return_value=RSS_END+1):
            self.assertEqual(await self.core.knowledge.import_sources({'kind':'reddit','query':'learnpython'}),[])
        self.assertEqual(api.await_count,0);self.assertIn('accesso approvato',self.core.knowledge.snapshot()['jobs'][0]['detail'])

    async def test_explicit_public_reddit_search_imports_that_provider(self):
        api=self.core.learning.public_get=AsyncMock(return_value=feed('dadjokes'))
        await self.core.knowledge.lookup('Cerca su r/dadjokes')
        self.assertIn('/r/dadjokes/',api.await_args.args[0]);self.assertEqual(self.core.knowledge.snapshot()['reddit']['documents'],1)
