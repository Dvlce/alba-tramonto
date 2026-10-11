import asyncio
import base64
import json
import unittest
from unittest.mock import AsyncMock,Mock
import test_core
from core.knowledge import source_request, words
from core.training_data import curriculum, validation, LANGUAGE_HOLDOUT, HOLDOUT


class SourceValidationTests(unittest.TestCase):
    def test_only_public_provider_urls_and_bounded_requests(self):
        self.assertEqual(source_request({'kind': 'wikipedia', 'query': 'https://en.wikipedia.org/wiki/Python_(programming_language)'})['language'], 'en')
        self.assertEqual(source_request({'kind': 'github', 'query': 'https://github.com/pallets/flask.git'})['query'], 'pallets/flask')
        self.assertEqual(source_request({'kind':'wikipedia','query':'Articolo','language':'be-tarask'})['language'],'be-tarask')
        for value in ({'kind':'wikipedia','query':'https://127.0.0.1/wiki/a'},
                      {'kind':'wikipedia','query':'https://it.wikipedia.org.evil.test/wiki/a'},
                      {'kind':'wikipedia','query':'https://it.wikipedia.org:443/wiki/a'},
                      {'kind':'wikipedia','query':'a','language':'it/../localhost'},
                      {'kind':'wikipedia','query':'a','count':True},
                      {'kind':'github','query':'a/b;id'}):
            with self.assertRaises(ValueError):source_request(value)

    def test_curriculum_has_language_and_no_holdout_prompt_leakage(self):
        rows=curriculum([]);prompts={r['prompt'] for r in rows}
        self.assertGreaterEqual(len(rows),44)
        self.assertEqual({r['task'] for r in rows},{'code','language'})
        self.assertTrue(all(r['system'] for r in rows))
        self.assertFalse(prompts & {p for p,_ in HOLDOUT})
        self.assertFalse(prompts & {r['prompt'] for r in LANGUAGE_HOLDOUT})
        self.assertEqual(len(validation()),10)
        self.assertEqual(words('È una lezione: l’italiano, Python 3!'),6)


class KnowledgeTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=test_core.CoreTests.asyncSetUp
    asyncTearDown=test_core.CoreTests.asyncTearDown
    req=test_core.CoreTests.req

    async def test_teaching_is_private_immediately_retrieved_and_deduplicated(self):
        lesson={'title':'Regola della galassia','text':'Il codice della galassia è NEBULA-42.',
                'question':'Qual è il codice della galassia?','answer':'NEBULA-42.'}
        self.assertEqual((await self.req('/api/notte/knowledge','POST',lesson,uid=2)).status,403)
        response=await self.req('/api/notte/knowledge','POST',lesson);self.assertEqual(response.status,201)
        remembered=await self.core.retrieve('codice della galassia',prefer_lexical=True)
        self.assertIn('NEBULA-42',remembered[0]['content'])
        await self.req('/api/notte/knowledge','POST',lesson)
        state=self.core.knowledge.snapshot();self.assertEqual(state['documents'],1)
        self.assertEqual(state['indexed_percent'],100);self.assertEqual(state['teaching_pairs'],1)
        self.assertEqual(self.core.knowledge.training_examples()[0]['answer'],'NEBULA-42.')
        self.core.configure({'connectors':{'files':False}})
        self.assertEqual(await self.core.retrieve('galassia',prefer_lexical=True),[])

    async def test_lesson_update_replaces_old_chunks_without_duplicating_counts(self):
        k=self.core.knowledge
        first=k.teach({'title':'Nome stella','text':'La stella si chiama Antares.'})
        second=k.teach({'title':'Nome stella','text':'La stella si chiama Sirio.'})
        self.assertEqual(first['id'],second['id'])
        self.assertEqual(k.snapshot()['documents'],1)
        chunks=' '.join(r['content'] for r in self.store.rows('SELECT content FROM core_chunks'))
        self.assertIn('Sirio',chunks);self.assertNotIn('Antares',chunks)
        response=await self.req('/api/notte/knowledge','POST',{'title':'a','text':'b','question':'c'})
        self.assertEqual(response.status,400);self.assertIn('risposta', (await response.json())['error'])

    async def test_full_wikipedia_document_revision_and_provenance(self):
        content='Python è un linguaggio di programmazione. '*100
        self.core.learning.public_get=AsyncMock(side_effect=[
            json.dumps({'query':{'search':[{'pageid':10,'title':'Python'}]}}).encode(),
            json.dumps({'query':{'pages':[{'pageid':10,'title':'Python','extract':content,
                       'fullurl':'https://it.wikipedia.org/wiki/Python','revisions':[{'revid':99}]}]}}).encode()])
        self.core.knowledge.start({'kind':'wikipedia','query':'Python'})
        await self.core.knowledge.task
        state=self.core.knowledge.snapshot();self.assertEqual(state['jobs'][0]['status'],'ready')
        self.assertEqual(state['sources'][0]['revision'],'99')
        self.assertEqual(state['words'],words(content))
        self.assertGreater(len(self.store.rows('SELECT * FROM core_chunks')),1)
        self.assertEqual(state['progress']['percent'],100)
        self.assertIn('url',self.core.knowledge.retrieve('Python')[0])

    async def test_github_reads_public_text_and_refreshes_changed_commit(self):
        sha='a'*40;blob='b'*40
        text='This repository explains clear Python functions and useful web applications. '*4
        api=AsyncMock(side_effect=[json.dumps({'default_branch':'main','license':{'spdx_id':'MIT'}}).encode(),
            json.dumps({'sha':sha}).encode(),json.dumps({'tree':[{'path':'README.md','type':'blob','size':400,'sha':blob},
                {'path':'.env','type':'blob','size':10,'sha':blob}]}).encode(),
            json.dumps({'encoding':'base64','content':base64.b64encode(text.encode()).decode()}).encode()])
        self.core.learning.public_get=api
        await self.core.knowledge.import_sources({'kind':'github','query':'example/library'})
        self.assertEqual(len(self.core.knowledge.snapshot()['sources']),1)
        self.assertEqual(self.core.knowledge.training_examples()[0]['license'],'MIT')
        self.assertTrue(all(call.args[0].startswith('https://api.github.com/') for call in api.await_args_list))
        api.side_effect=[json.dumps({'default_branch':'main'}).encode(),json.dumps({'sha':sha}).encode()]
        await self.core.knowledge.import_sources({'kind':'github','query':'example/library'})
        self.assertEqual(api.await_count,6) # unchanged revision doesn't re-fetch blobs

    async def test_failed_import_and_cancel_keep_partial_progress_truthful(self):
        self.core.learning.public_get=AsyncMock(side_effect=ValueError('HTTP 429: quota'))
        await self.core.knowledge.import_sources({'kind':'wikipedia','query':'Python'})
        state=self.core.knowledge.snapshot();self.assertEqual(state['jobs'][0]['status'],'error')
        self.assertEqual(state['progress']['percent'],0);self.assertEqual(state['documents'],0)
        began=asyncio.Event()
        async def blocked(*a,**k):began.set();await asyncio.Event().wait()
        self.core.learning.public_get=blocked
        self.core.knowledge.start({'kind':'wikipedia','query':'Python'});await began.wait()
        await self.core.knowledge.stop()
        self.assertEqual(self.core.knowledge.snapshot()['jobs'][0]['status'],'interrupted')
        self.assertFalse(self.core.knowledge.importing)

    async def test_large_lesson_is_accepted_within_the_document_limit(self):
        response=await self.req('/api/notte/knowledge','POST',{'title':'Lezione lunga','text':'è '*15000})
        self.assertEqual(response.status,201)
        self.assertEqual((await response.json())['words'],15000)

    async def test_ordinary_chat_uses_validated_model_when_enabled(self):
        self.core.config.update(personal_model='notte-personal:20261010-16',personal_enabled=True)
        await self.core.work('chat','Ciao')
        payload=next(p for url,p in self.model.calls if url.endswith('/api/chat'))
        self.assertEqual(payload['model'],'notte-personal:20261010-16')
        self.assertEqual(self.core.resources()['model'],payload['model'])

    async def test_external_text_is_not_treated_as_verified_code(self):
        k=self.core.knowledge
        k.remember('github','owner/repo/danger.py','owner/repo · danger.py','exec("untrusted code")','https://github.com/owner/repo','a'*40,'MIT')
        k.teach({'title':'Memoria','text':'Questo testo resta in memoria senza cambiare i pesi.'})
        self.assertEqual(k.training_examples(),[])
        self.assertEqual((await self.req('/api/notte/knowledge',uid=2)).status,403)

    async def test_public_reader_identifies_the_project_to_wikimedia(self):
        from types import SimpleNamespace
        async def chunks():yield b'{"query":{}}'
        response=test_core.Response({});response.content=SimpleNamespace(iter_chunked=lambda _:chunks())
        self.model.get=Mock(return_value=response)
        result=await self.core.learning.public_get('https://it.wikipedia.org/w/api.php')
        self.assertEqual(result,b'{"query":{}}')
        headers=self.model.get.call_args.kwargs['headers']
        self.assertIn('https://github.com/Dvlce/alba-tramonto',headers['User-Agent'])
        self.assertEqual(self.model.get.call_args.kwargs['allow_redirects'],False)

    async def test_long_source_embeddings_match_stored_chunks_and_finish_in_batches(self):
        self.core.knowledge.teach({'title':'Documento esteso','text':'Una lezione sulle galassie e sulle stelle. '*600})
        source=self.store.rows('SELECT event_id FROM core_knowledge')[0]['event_id']
        chunks=self.store.rows('SELECT content FROM core_chunks WHERE event_id=? ORDER BY part',(source,))
        async def embed(texts):return [[.1,.2] for _ in texts]
        self.core.embed=AsyncMock(side_effect=embed)
        self.core.generate=AsyncMock(return_value=test_core.output())
        await self.core.consolidate()
        self.assertEqual(self.core.embed.await_args_list[0].args[0],[r['content'] for r in chunks[:12]])
        self.assertEqual(self.store.rows('SELECT count(*) n FROM core_chunks WHERE event_id=? AND embedding IS NOT NULL',(source,))[0]['n'],12)
        for _ in range(3):await self.core.consolidate()
        self.assertEqual(self.store.rows('SELECT count(*) n FROM core_chunks WHERE event_id=? AND embedding IS NULL',(source,))[0]['n'],0)


class TrainingPromotionTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=test_core.CoreTests.asyncSetUp
    asyncTearDown=test_core.CoreTests.asyncTearDown

    async def candidate(self,language_passed):
        training=self.core.training
        self.model.get=Mock(return_value=test_core.Response({'models':[]}))
        before={'passed':4,'total':4,'language_passed':5,'language_total':6,'tokens_per_second':12,'success_percent':90}
        after={**before,'language_passed':language_passed,'tokens_per_second':13}
        training.benchmark=AsyncMock(side_effect=[before,after]);training.prune_versions=AsyncMock()
        async def worker(work,previous):
            (work/'merged').mkdir();(work/'adapter').mkdir()
            (work/'report.json').write_text(json.dumps({'accepted':True,'initial_loss':2,'final_loss':1,'steps':12}))
            return 0
        async def process(args,*unused,**kwargs):
            from pathlib import Path
            if '--outfile' in args:Path(args[args.index('--outfile')+1]).write_bytes(b'f16')
            elif 'Q4_K_M' in args:Path(args[2]).write_bytes(b'q4')
            return 0,'OK'
        training.execute=worker;self.core.learning.bounded_process=process
        await training.run()
        return self.store.rows('SELECT * FROM core_training ORDER BY id DESC')[0]

    async def test_validated_candidate_becomes_the_ordinary_notte_model(self):
        row=await self.candidate(5)
        self.assertEqual(row['status'],'ready')
        self.assertTrue(self.core.config['personal_enabled'])
        self.assertEqual(self.core.config['personal_adapter'],str(row['id']))
        self.assertTrue(json.loads(row['metrics'])['promoted'])
        self.assertIn('before_benchmark',json.loads(row['metrics']))

    async def test_language_regression_is_rejected_even_when_python_passes(self):
        self.core.config.update(personal_model='notte-personal:20261004-7',personal_adapter='7')
        row=await self.candidate(4)
        self.assertEqual(row['status'],'rejected')
        self.assertEqual(self.core.config['personal_adapter'],'7')
        self.assertFalse(json.loads(row['metrics'])['promoted'])

    async def test_training_preserves_an_explicit_chat_model_preference(self):
        self.core.configure({'personal_enabled':False})
        row=await self.candidate(5)
        self.assertEqual(row['status'],'ready')
        self.assertFalse(self.core.config['personal_enabled'])

    async def test_daily_training_waits_for_new_examples(self):
        training=self.core.training;training.ready=lambda:True
        self.core.config['training_hour']=0
        digest=training.dataset_digest(training.dataset())
        self.store.execute('INSERT INTO core_training(day,started,status,dataset_hash) VALUES(?,?,?,?)',('2000-01-01',1,'ready',digest))
        self.assertFalse(training.due())
        self.core.knowledge.teach({'title':'Lezione nuova','text':'Il progetto si chiama Nebula.', 'question':'Come si chiama il progetto?','answer':'Nebula.'})
        self.assertTrue(training.due())
