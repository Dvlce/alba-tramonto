import asyncio
import json
import os
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from core.gguf_plan import GIB, inspect_gguf, plan
from core.prepare_ssd import digest, register
from core.ssd_runtime import SSDRuntime, command
from core.inference import cache_friendly_messages


def gguf(moe=False):
    string=lambda v:struct.pack('<Q',len(v))+v.encode()
    values={'general.architecture':'qwen2moe' if moe else 'qwen2',
            ('qwen2moe' if moe else 'qwen2')+'.block_count':2,
            ('qwen2moe' if moe else 'qwen2')+'.embedding_length':128,
            ('qwen2moe' if moe else 'qwen2')+'.attention.head_count':4,
            ('qwen2moe' if moe else 'qwen2')+'.attention.head_count_kv':2}
    if moe:values.update({'qwen2moe.expert_count':8,'qwen2moe.expert_used_count':2})
    data=b'GGUF'+struct.pack('<IQQ',3,2,len(values))
    for k,v in values.items():
        data+=string(k)+struct.pack('<I',8 if isinstance(v,str) else 4)+(string(v) if isinstance(v,str) else struct.pack('<I',v))
    for name,shape,offset in [('token_embd.weight',[8,8],0),
                              ('blk.0.ffn_up_exps.weight' if moe else 'blk.0.ffn_up.weight',[8,8,8] if moe else [8,8],256)]:
        data+=string(name)+struct.pack('<I',len(shape))+b''.join(struct.pack('<Q',n) for n in shape)+struct.pack('<IQ',0,offset)
    data+=b'\0'*((-len(data))%32)+b'\0'*2304
    return data


class PlannerTests(unittest.TestCase):
    def test_emotion_updates_keep_cached_prefix_and_preserve_all_state(self):
        base=[{'role':'system','content':'Persona\nSTATO E MEMORIA:\n{"emotion":0.4,"memory":"user fact"}'},
              {'role':'user','content':'earlier question'},{'role':'assistant','content':'earlier answer'},
              {'role':'user','content':'current question'}]
        first=cache_friendly_messages(base)
        changed=[dict(m) for m in base];changed[0]['content']=changed[0]['content'].replace('0.4','0.5')
        second=cache_friendly_messages(changed)
        self.assertEqual(first[:-1],second[:-1])
        self.assertIn('{"emotion":0.4,"memory":"user fact"}',first[-1]['content'])
        self.assertIn('{"emotion":0.5,"memory":"user fact"}',second[-1]['content'])
        self.assertTrue(first[-1]['content'].startswith('current question'))
        self.assertEqual(first[1:3],base[1:3]);self.assertIn('STATO E MEMORIA',base[0]['content'])

    def test_dense_and_moe_actual_tensor_index(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'model.gguf'
            path.write_bytes(gguf());info=inspect_gguf(path)
            dense=plan(info,8*GIB,6*GIB)
            self.assertFalse(dense['recognized_moe_tensors'])
            self.assertEqual(dense['estimated_active_weight_bytes'],path.stat().st_size)
            path.write_bytes(gguf(True));moe=plan(inspect_gguf(path),8*GIB,6*GIB)
            self.assertTrue(moe['recognized_moe_tensors'])
            self.assertEqual(moe['active_experts'],2)
            self.assertEqual(moe['estimated_active_weight_bytes'],moe['dense_bytes']+512)
            self.assertFalse(moe['weights_changed']);self.assertEqual(moe['cache_type'],'f16')

    def test_dense_larger_than_ram_is_not_claimed_resident(self):
        result=plan({'file_bytes':12*GIB,'metadata':{'general.architecture':'qwen2'},'tensors':[]},8*GIB,6*GIB)
        self.assertEqual(result['classification'],'disk_bound');self.assertEqual(result['policy'],'mapped')
        self.assertEqual(result['estimated_active_weight_bytes'],12*GIB)

    def test_repacking_budget_counts_transient_duplicate(self):
        result=plan({'file_bytes':5*GIB,'metadata':{'general.architecture':'qwen2'},'tensors':[]},8*GIB,7*GIB)
        self.assertEqual(result['classification'],'resident')
        self.assertFalse(result['repack_peak_fits']);self.assertEqual(result['policy'],'mapped')

    def test_truncated_untrusted_gguf_and_bounds(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'model.gguf'
            for raw in (b'',b'GGUF'+struct.pack('<IQQ',3,100001,0),gguf()[:-2200]):
                path.write_bytes(raw)
                with self.assertRaises(ValueError):inspect_gguf(path)
        with self.assertRaises(ValueError):plan({},8*GIB,6*GIB,8192)

    def test_import_verifies_original_and_never_writes_weights(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);ollama=root/'ollama';runtime=root/'runtime'
            blob_dir=ollama/'blobs';blob_dir.mkdir(parents=True)
            data=gguf();import hashlib
            sha=hashlib.sha256(data).hexdigest();blob=blob_dir/('sha256-'+sha);blob.write_bytes(data);blob.chmod(0o644)
            manifest=ollama/'manifests/registry.ollama.ai/library/qwen2/7b';manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({'layers':[{'mediaType':'application/vnd.ollama.image.model','digest':'sha256:'+sha,'size':len(data)}]}))
            model=register(runtime,ollama,'qwen2:7b')
            self.assertEqual(digest(blob),model['sha256'])
            self.assertEqual(blob.stat().st_ino,(runtime/'models'/model['file']).stat().st_ino)
            with self.assertRaises(ValueError):register(runtime,ollama,'../../etc/passwd')
            blob.write_bytes(b'bad')
            with self.assertRaises(ValueError):register(runtime,ollama,'qwen2:7b')

    def test_policy_never_requantizes_and_rejects_arbitrary_flags(self):
        args=command('llama-server','target.gguf','mapped',1024,'server.key')
        self.assertIn('--no-repack',args);self.assertIn('--no-context-shift',args)
        self.assertEqual(args[args.index('--cache-type-k')+1],'f16')
        with self.assertRaises(ValueError):command('x','y','--shell',1024,'key')
        with self.assertRaises(ValueError):command('x','y','speculative',1024,'key')
        spec=command('x','target','speculative',1024,'key',draft='draft')
        self.assertIn('--no-repack',spec)
        self.assertEqual(spec[spec.index('--model')+1],'target')
        self.assertEqual(spec[spec.index('--model-draft')+1],'draft')


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_sse_is_drained_before_checkpoint_save(self):
        with tempfile.TemporaryDirectory() as temporary:
            ended=False
            class Response:
                status=200
                async def __aenter__(self):return self
                async def __aexit__(self,*args):pass
                def __init__(self):self.content=self
                def __aiter__(self):
                    async def lines():
                        nonlocal ended
                        yield b'data: {"choices":[{"delta":{"content":"42"}}],"usage":{"prompt_tokens":47,"completion_tokens":3}}\n'
                        yield b'data: [DONE]\n'
                        ended=True
                    return lines()
            core=SimpleNamespace(settings=SimpleNamespace(data=Path(temporary)),config={'ssd_policy':'auto'},
                 engine=SimpleNamespace(session=SimpleNamespace(post=lambda *args,**kwargs:Response())),
                 event=lambda *args:None,tokens=lambda *args:None,partial='')
            runtime=SSDRuntime(core);runtime.planning=lambda *args:{'policy':'mapped'}
            runtime.catalog=lambda:{'large':{'sha256':'a'*64}}
            runtime.start=AsyncMock();runtime.stop=AsyncMock()
            async def checkpoint(model,policy,context,action):
                if action=='save':self.assertTrue(ended)
            runtime.checkpoint=AsyncMock(side_effect=checkpoint)
            await runtime.chat('large',[{'role':'user','content':'17+25'}],12,1024)
            self.assertEqual(core.partial,'42');runtime.stop.assert_awaited_once()

    async def test_stop_kills_process_group_and_cleans_key(self):
        with tempfile.TemporaryDirectory() as temporary:
            core=SimpleNamespace(settings=SimpleNamespace(data=Path(temporary)))
            runtime=SSDRuntime(core);runtime.root.mkdir();(runtime.root/'server.key').write_text('private')
            runtime.process=await asyncio.create_subprocess_exec('/bin/sleep','30',start_new_session=True)
            process=runtime.process
            await runtime.stop()
            self.assertIsNotNone(process.returncode);self.assertIsNone(runtime.process)
            self.assertFalse((runtime.root/'server.key').exists())

    async def test_critical_ram_stops_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            core=SimpleNamespace(settings=SimpleNamespace(data=Path(temporary)))
            runtime=SSDRuntime(core);runtime.process=SimpleNamespace(pid=12345,returncode=None)
            def read(path,*args,**kwargs):
                if str(path).endswith('/status'):return 'VmRSS: 10 kB\nRssAnon: 10 kB\nVmSwap: 0 kB\n'
                if str(path).endswith('/io'):return 'read_bytes: 4096\n'
                return '50000'
            with patch('core.ssd_runtime.memory',return_value=(8*GIB,100*1024**2)),patch.object(Path,'read_text',read),patch('os.killpg') as kill:
                await runtime.monitor()
                kill.assert_called_once();self.assertIn('512 MiB',runtime.failure)

    async def test_model_catalog_cannot_redirect_to_private_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime=SSDRuntime(SimpleNamespace(settings=SimpleNamespace(data=Path(temporary))))
            runtime.root.mkdir();(runtime.root/'models.json').write_text(json.dumps({'bad':{'file':'../../auth.key','sha256':'a'*64,'size':4}}))
            with self.assertRaises(ValueError):runtime.model_path('bad')

    async def test_cache_is_bound_to_target_revision_context_and_policy(self):
        with tempfile.TemporaryDirectory() as temporary:
            core=SimpleNamespace(settings=SimpleNamespace(data=Path(temporary)),event=lambda *args:None)
            runtime=SSDRuntime(core);runtime.root.mkdir()
            (runtime.root/'models.json').write_text(json.dumps({'large':{'sha256':'a'*64},'other':{'sha256':'b'*64}}))
            self.assertNotEqual(runtime.cache_name('large','mapped',1024),runtime.cache_name('other','mapped',1024))
            self.assertNotEqual(runtime.cache_name('large','mapped',1024),runtime.cache_name('large','mapped',2048))
            self.assertNotEqual(runtime.cache_name('large','mapped',1024),runtime.cache_name('large','speculative',1024))
            self.assertFalse(await runtime.checkpoint('large','mapped',1024,'restore'))
            with self.assertRaises(ValueError):runtime.cache_name('large','../../auth',1024)
            with self.assertRaises(ValueError):await runtime.checkpoint('large','mapped',1024,'delete')

    async def test_checkpoint_is_atomic_and_corruption_is_recoverable(self):
        with tempfile.TemporaryDirectory() as temporary:
            events=[]
            core=SimpleNamespace(settings=SimpleNamespace(data=Path(temporary)),event=lambda *args:events.append(args))
            runtime=SSDRuntime(core);runtime.root.mkdir();runtime.cache_dir.mkdir()
            (runtime.root/'models.json').write_text(json.dumps({'large':{'sha256':'a'*64}}))
            class Response:
                status=200
                async def __aenter__(self):return self
                async def __aexit__(self,*args):pass
                async def json(self):return {'n_saved':17}
            def post(url,headers,json,timeout):
                (runtime.cache_dir/json['filename']).write_bytes(b'valid-checkpoint')
                return Response()
            core.engine=SimpleNamespace(session=SimpleNamespace(post=post))
            self.assertTrue(await runtime.checkpoint('large','mapped',1024,'save'))
            saved=runtime.cache_dir/runtime.cache_name('large','mapped',1024)
            self.assertEqual(saved.read_bytes(),b'valid-checkpoint')
            self.assertEqual(saved.stat().st_mode&0o777,0o600)
            self.assertFalse(list(runtime.cache_dir.glob('*.tmp')))
            class ErrorResponse(Response):
                status=400
                async def json(self):return {'error':{'message':'invalid slot state'}}
            core.engine.session.post=lambda *args,**kwargs:ErrorResponse()
            self.assertFalse(await runtime.checkpoint('large','mapped',1024,'restore'))
            self.assertFalse(saved.exists())
            self.assertIn('invalid slot state',events[-1][-1])
