import asyncio
import json
import time
import unittest
from unittest.mock import AsyncMock,patch
import test_core
from core.learning import reddit_entries,LESSONS
from core.training_data import examples,HOLDOUT

class SelfLearningTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=test_core.CoreTests.asyncSetUp
    asyncTearDown=test_core.CoreTests.asyncTearDown
    req=test_core.CoreTests.req

    async def test_training_access_and_missing_environment(self):
        response=await self.req('/api/notte/training/1',uid=2);self.assertEqual(response.status,403)
        response=await self.req('/api/notte/action','POST',{'action':'train'});self.assertEqual(response.status,403)
        self.assertFalse(self.core.training.snapshot()['ready'])
        response=await self.req('/api/notte/action','POST',{'action':'config','config':{'training_hour':24}});self.assertEqual(response.status,403)
        response=await self.req('/api/notte/action','POST',{'action':'config','config':{'training_hour':7,'training_enabled':False}});self.assertEqual(response.status,200)
        self.assertFalse(self.core.config['training_enabled'])

    async def test_activity_contains_starts_failures_and_interruptions(self):
        self.core.learning.reddit=AsyncMock(side_effect=ValueError('HTTP 429'))
        await self.core.work('reddit')
        response=await self.req('/api/notte/events?category=all');events=(await response.json())['events']
        self.assertTrue(any(e['role']=='start' and e['category']=='activity' for e in events))
        self.assertTrue(any(e['role']=='error' and '429' in e['content'] for e in events))
        response=await self.req('/api/notte/events?category=all',uid=2);self.assertEqual(response.status,403)

    async def test_feed_filters_external_links_and_strips_html(self):
        feed=b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Python</title><link href="https://www.reddit.com/r/learnpython/comments/abc/"/><content type="html">&lt;b&gt;Example&lt;/b&gt; &amp;amp; code</content></entry><entry><title>Private</title><link href="http://127.0.0.1/secret"/></entry></feed>'''
        rows=reddit_entries(feed);self.assertEqual(len(rows),1);self.assertEqual(rows[0]['excerpt'],'Example & code')

    async def test_complete_activity_history_with_private_bounded_cursor(self):
        for i in range(205):self.core.event('notes','note',str(i))
        response=await self.req('/api/notte/events?category=all');newest=await response.json()
        self.assertEqual(len(newest['events']),100)
        response=await self.req('/api/notte/events?category=all&before='+str(newest['before']));older=await response.json()
        self.assertEqual(len(older['events']),100)
        self.assertLess(older['events'][-1]['id'],newest['events'][0]['id'])
        response=await self.req('/api/notte/events?category=all&before='+str(older['before']));oldest=await response.json()
        self.assertEqual(len(oldest['events']),5)
        for query in ('before=-1','before=bad','before=1&after=1'):
            self.assertEqual((await self.req('/api/notte/events?'+query)).status,403)
        self.assertEqual((await self.req('/api/notte/events?category=all&before=100',uid=2)).status,403)

    async def test_reddit_dedup_and_diary_do_not_claim_tested_learning(self):
        self.core.learning.public_get=AsyncMock(return_value=b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Python</title><link href="https://www.reddit.com/r/learnpython/comments/abc/"/><content>Discuss functions.</content></entry></feed>')
        await self.core.learning.reddit();await self.core.learning.reddit()
        self.assertEqual(self.store.rows('SELECT count(*) n FROM core_reddit')[0]['n'],1)
        diary=self.core.learning.diary();self.assertEqual(len(diary),1);self.assertEqual(diary[0]['status'],'read')
        self.assertTrue(all(r['origin']=='project-authored' for r in examples(diary)))
        self.assertGreater(self.core.config['last_reddit'],0)

    async def test_only_verified_curriculum_is_training_target(self):
        entry={'id':9,'title':LESSONS[0]['function'],'code':'def count_words(text): return {}','status':'failed'}
        baseline=len(examples([]));self.assertEqual(len(examples([entry])),baseline)
        entry['status']='verified';self.assertEqual(len(examples([entry])),baseline+1)
        row=examples([entry])[-1];self.assertEqual(row['source_id'],9)
        self.assertFalse(set(p for p,a in HOLDOUT)&set(r['prompt'] for r in examples([entry])))

    async def test_fast_chat_avoids_query_embedding_model_swap(self):
        self.service.performance.snapshot={'ram':{'percent':20},'cpu_percent':99,'temperature_c':50}
        self.core.event('files','document','Telescopio osservatorio galassie.')
        await self.core.work('consolidation');self.model.calls.clear()
        await self.core.work('chat','Raccontami delle galassie.')
        self.assertEqual(self.core.error,'')
        self.assertFalse(any(url.endswith('/api/embed') for url,body in self.model.calls))
        payload=next(body for url,body in self.model.calls if url.endswith('/api/chat'))
        self.assertEqual(payload['model'],'qwen2.5:1.5b');self.assertLessEqual(payload['options']['num_ctx'],1536)
        self.assertTrue(payload['options']['use_mmap'])
        self.assertTrue(self.store.rows("SELECT * FROM core_events WHERE role='latency'"))

    async def test_quality_and_personal_model_routing(self):
        self.core.configure({'profile':'quality'})
        await self.core.work('chat','Una domanda semplice.')
        payload=next(body for url,body in self.model.calls if url.endswith('/api/chat'))
        self.assertEqual(payload['model'],self.settings.model)
        self.core.config['personal_model']='notte-personal:20261004-1';self.model.calls.clear()
        await self.core.work('personal_chat','Scrivi codice Python.')
        payload=next(body for url,body in self.model.calls if url.endswith('/api/chat'))
        self.assertEqual(payload['model'],'notte-personal:20261004-1')

    async def test_invalid_rollback_cannot_select_arbitrary_model(self):
        response=await self.req('/api/notte/action','POST',{'action':'rollback','id':'../1'});self.assertEqual(response.status,403)
        self.assertEqual(self.core.config['personal_model'],'')

    async def test_model_can_choose_wake_and_study(self):
        from test_core import output
        self.core.learning.study=AsyncMock();value=output();value.update(action='study',wake_minutes=1)
        before=time.time();await self.core.accept(value,'reflection')
        self.core.learning.study.assert_awaited_once();self.assertAlmostEqual(self.core.config['next_reflection']-before,60,delta=2)
