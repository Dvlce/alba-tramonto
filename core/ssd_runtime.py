"""Same-GGUF CPU runtime: bounded mmap, native kernels and verified speculation.

This is a llama.cpp integration, not a universal Colibri implementation. Dense
weights are never skipped. Policies never requantize weights or the f16 KV.
"""
import asyncio
import json
import os
import secrets
import signal
import time
from pathlib import Path
from aiohttp import ClientError
from .gguf_plan import GIB, inspect_gguf, plan
from .prepare_conversion import LLAMA_REVISION

POLICIES=('native','mapped','speculative')


def memory():
    fields={line.split(':',1)[0]:int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines()}
    return fields['MemTotal'],fields['MemAvailable']


def command(binary,model,policy,context,key,port=8092,draft=None,slots=None):
    if policy not in POLICIES or type(context) is not int or not 512<=context<=4096:raise ValueError('Policy SSD non valida.')
    args=[str(binary),'--model',str(model),'--host','127.0.0.1','--port',str(port),
          '--api-key-file',str(key),'--threads','4','--threads-batch','4','--poll','0',
          '--ctx-size',str(context),'--parallel','1','--batch-size','128','--ubatch-size','128',
          '--load-mode','mmap','--fit','off','--n-gpu-layers','0','--cache-type-k','f16','--cache-type-v','f16',
          '--cache-ram','0','--no-context-shift','--no-warmup','--jinja','--metrics',
          '--flash-attn','on']
    if policy in ('mapped','speculative'):args+=['--no-repack']
    if slots:args+=['--slots','--slot-save-path',str(slots)+'/' ]
    if policy=='speculative':
        if not draft:raise ValueError('Modello draft non preparato.')
        args+=['--spec-type','draft-simple','--model-draft',str(draft),
               '--spec-draft-n-max','4','--spec-draft-n-min','1','--spec-draft-threads','2']
    return args


class SSDRuntime:
    def __init__(self,core):
        self.core=core;self.root=core.settings.data/'core-inference'
        self.binary=self.root/'build/bin/llama-server';self.process=None;self.watch=None
        self.peak={};self.failure='';self.key='';self.info_cache={}
        self.cache_dir=self.root/'kv-cache'

    def catalog(self):
        path=self.root/'models.json'
        if not path.is_file():return {}
        if path.stat().st_size>262144:raise ValueError('Catalogo SSD troppo grande.')
        models=json.loads(path.read_text())
        if not isinstance(models,dict) or len(models)>64:raise ValueError('Catalogo SSD non valido.')
        return models

    def model_path(self,name):
        import re
        entry=self.catalog().get(name)
        if not entry or not re.fullmatch('[0-9a-f]{64}',entry.get('sha256','')):raise ValueError('Prepara prima il GGUF di '+str(name)[:100])
        if entry.get('file')!=entry['sha256']+'.gguf':raise ValueError('Percorso GGUF non valido.')
        path=self.root/'models'/entry['file']
        if path.is_symlink() or not path.is_file() or path.stat().st_size!=entry['size']:raise ValueError('GGUF modificato o assente.')
        return path

    def snapshot(self):
        return {'ready':self.binary.is_file(),'revision':LLAMA_REVISION,'models':list(self.catalog()),
                'running':bool(self.process and self.process.returncode is None),'peak':self.peak,
                'failure':self.failure,'policies':list(POLICIES),'weights_changed':False,'kv_cache':'f16'}

    def planning(self,name,context=1024):
        path=self.model_path(name);stat=path.stat();key=(str(path),stat.st_size,stat.st_mtime_ns)
        if key not in self.info_cache:
            self.info_cache.clear();self.info_cache[key]=inspect_gguf(path)
        total,available=memory()
        return {'model':name,'sha256':self.catalog()[name]['sha256'],**plan(self.info_cache[key],total,available,context)}

    async def unload_ollama(self):
        # Called under Alba's shared inference lock. Avoid two resident runtimes.
        async with self.core.engine.session.get(self.core.settings.llm_url+'/api/ps',timeout=15) as response:
            if response.status!=200:raise ValueError('Inventario dei modelli residenti non disponibile.')
            models=(await response.json()).get('models',[])
        for item in models:
            async with self.core.engine.session.post(self.core.settings.llm_url+'/api/generate',
                      json={'model':item['name'],'keep_alive':0},timeout=30) as response:
                if response.status!=200:raise ValueError('Impossibile liberare il modello residente.')
                await response.read()

    async def monitor(self):
        proc=self.process
        while proc.returncode is None:
            try:
                _,available=memory()
                status=Path('/proc')/str(proc.pid)/'status'
                fields={line.split(':',1)[0]:line.split(':',1)[1].strip() for line in status.read_text().splitlines()}
                for field,key in (('VmRSS','rss_bytes'),('RssAnon','anonymous_bytes'),('VmSwap','swap_bytes')):
                    self.peak[key]=max(self.peak.get(key,0),int(fields.get(field,'0').split()[0])*1024)
                self.peak['minimum_available_bytes']=min(self.peak.get('minimum_available_bytes',available),available)
                io=Path('/proc')/str(proc.pid)/'io'
                self.peak['disk_read_bytes']=int(next(line.split()[1] for line in io.read_text().splitlines() if line.startswith('read_bytes:')))
                temperature=Path('/sys/class/thermal/thermal_zone0/temp')
                temp=float(temperature.read_text())/1000 if temperature.exists() else 0
                self.peak['temperature_c']=max(self.peak.get('temperature_c',0),temp)
                if available<512*1024**2:self.failure='Memoria libera sotto 512 MiB: esecuzione interrotta, dati conservati.'
                elif self.peak.get('swap_bytes',0)>512*1024**2:self.failure='Runtime oltre 512 MiB di swap: interrotto per evitare thrashing.'
                elif temp>=80:self.failure='Temperatura oltre 80 °C: esecuzione interrotta.'
                if self.failure:
                    os.killpg(proc.pid,signal.SIGTERM);return
            except (OSError,ValueError,StopIteration):
                if proc.returncode is not None:return
            await asyncio.sleep(.2)

    async def start(self,name,policy='native',context=1024,draft_name='qwen2.5-coder:0.5b'):
        self.peak={};self.failure=''
        if not self.binary.is_file():raise ValueError('Runtime CPU SSD non preparato.')
        if self.process and self.process.returncode is None:raise ValueError('Runtime SSD già in corso.')
        target=self.model_path(name)
        draft=self.model_path(draft_name) if policy=='speculative' else None
        await self.unload_ollama()
        placement=self.planning(name,context)
        if policy=='native' and not placement['repack_peak_fits']:
            raise ValueError('Repacking richiederebbe una seconda copia completa dei pesi: usa mapped.')
        if policy=='speculative' and (placement['classification']!='resident' or
                target.stat().st_size+2*draft.stat().st_size+placement['kv_f16_estimate_bytes']+placement['runtime_allowance_bytes']>placement['ram_budget_bytes']):
            raise ValueError('Per questo modello serve la policy mapped; niente copie complete in RAM.')
        if memory()[1]<GIB:raise ValueError('Meno di 1 GiB disponibile per avviare il runtime.')
        self.peak={};self.failure='';self.key=secrets.token_urlsafe(32)
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        key_file=self.root/'server.key';key_file.touch(mode=0o600,exist_ok=True);key_file.write_text(self.key+'\n');key_file.chmod(0o600)
        log_path=self.root/'server.log';log_path.touch(mode=0o600,exist_ok=True)
        self.cache_dir.mkdir(mode=0o700,parents=True,exist_ok=True)
        with log_path.open('wb') as output:
            self.process=await asyncio.create_subprocess_exec(*command(self.binary,target,policy,context,key_file,draft=draft,slots=self.cache_dir),
                stdout=output,stderr=output,start_new_session=True,umask=0o077,
                env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':str(self.root),'USER':'alba','LC_ALL':'C.UTF-8'})
        self.watch=asyncio.create_task(self.monitor())
        started=time.monotonic()
        while time.monotonic()-started<120:
            if self.process.returncode is not None:
                raise ValueError(self.failure or 'Avvio llama.cpp fallito; consulta il log locale privato.')
            try:
                async with self.core.engine.session.get('http://127.0.0.1:8092/health',
                          headers=self.headers,timeout=2) as response:
                    if response.status==200:return placement
            except (OSError,asyncio.TimeoutError):pass
            await asyncio.sleep(.2)
        raise ValueError('Avvio del runtime oltre 120 secondi.')

    @property
    def headers(self):return {'Authorization':'Bearer '+self.key}

    def cache_name(self,model,policy,context,purpose='chat'):
        if policy not in POLICIES or type(context) is not int or not 512<=context<=4096:raise ValueError('Cache non valida.')
        if purpose not in ('chat','probe'):raise ValueError('Namespace cache non valido.')
        return self.catalog()[model]['sha256']+'-'+LLAMA_REVISION[:12]+'-'+purpose+'-'+policy+'-'+str(context)+'.bin'

    async def checkpoint(self,model,policy,context,action,purpose='chat'):
        if action not in ('save','restore'):raise ValueError('Azione cache non valida.')
        name=self.cache_name(model,policy,context,purpose);path=self.cache_dir/name
        if action=='restore' and (not path.is_file() or path.is_symlink()):return False
        filename=name+'.tmp' if action=='save' else name
        temporary=self.cache_dir/filename
        try:
            if action=='restore' and path.stat().st_size>512*1024**2:raise ValueError('Cache troppo grande.')
            async with self.core.engine.session.post('http://127.0.0.1:8092/slots/0?action='+action,
                      headers=self.headers,json={'filename':filename},timeout=15) as response:
                value=await response.json()
                if response.status!=200:raise ValueError('Checkpoint KV HTTP '+str(response.status)+': '+str(value.get('error',''))[:160])
            if action=='save':
                if not temporary.is_file() or temporary.is_symlink() or not 0<temporary.stat().st_size<=512*1024**2:
                    raise ValueError('Dimensione checkpoint KV non valida.')
                temporary.chmod(0o600);temporary.replace(path)
                cached=sorted(self.cache_dir.glob('*.bin'),key=lambda p:p.stat().st_mtime,reverse=True)
                size=0
                for saved in cached:
                    size+=saved.stat().st_size
                    if size>512*1024**2:saved.unlink()
            self.core.event('activity','ssd_cache',json.dumps({'action':action,'model':model,'context':context,
                'tokens':value.get('n_saved') if action=='save' else value.get('n_restored')}))
            return True
        except (ClientError,OSError,ValueError,asyncio.TimeoutError) as exc:
            if action=='save':temporary.unlink(missing_ok=True)
            else:path.unlink(missing_ok=True)
            self.core.event('activity','ssd_cache','Cache '+action+' non disponibile; archivio e modello conservati. '+str(exc)[:240])
            return False

    async def stop(self):
        if self.watch:
            self.watch.cancel();await asyncio.gather(self.watch,return_exceptions=True);self.watch=None
        if self.process and self.process.returncode is None:
            try:os.killpg(self.process.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:await asyncio.wait_for(self.process.wait(),10)
            except asyncio.TimeoutError:
                try:os.killpg(self.process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                await self.process.wait()
        self.process=None;self.key=''
        (self.root/'server.key').unlink(missing_ok=True)

    async def completion(self,prompt,output=96):
        started=time.monotonic()
        async with self.core.engine.session.post('http://127.0.0.1:8092/completion',headers=self.headers,
                  json={'prompt':prompt,'n_predict':output,'temperature':0,'seed':42,'cache_prompt':True,
                        'return_tokens':True,'stream':False},timeout=240) as response:
            if response.status!=200:raise ValueError(self.failure or 'Generazione SSD fallita: HTTP '+str(response.status))
            value=await response.json()
        if self.failure:raise ValueError(self.failure)
        value['wall_ms']=round((time.monotonic()-started)*1000)
        return value

    async def template(self,messages):
        async with self.core.engine.session.post('http://127.0.0.1:8092/apply-template',headers=self.headers,
                  json={'messages':messages,'add_generation_prompt':True},timeout=10) as response:
            if response.status!=200:raise ValueError('Template nativo del modello non disponibile.')
            return (await response.json())['prompt']

    async def chat(self,model,messages,maximum,context):
        started=time.monotonic();first=None;usage={};done=False;recorded=False
        try:
            placement=self.planning(model,context)
            policy=self.core.config.get('ssd_policy','auto')
            if policy=='auto':policy=placement['policy']
            await self.start(model,policy,context)
            await self.checkpoint(model,policy,context,'restore')
            self.core.event('activity','ssd_model',json.dumps({'model':model,'policy':policy,'plan':placement}))
            async with self.core.engine.session.post('http://127.0.0.1:8092/v1/chat/completions',headers=self.headers,
                      json={'model':model,'messages':messages,'max_tokens':maximum,'temperature':.65,
                            'stream':True,'cache_prompt':True,'stream_options':{'include_usage':True}},timeout=480) as response:
                if response.status!=200:raise ValueError('Chat SSD fallita: HTTP '+str(response.status))
                async for line in response.content:
                    if len(line)>65536:raise ValueError('Frame SSD troppo lungo.')
                    if not line.startswith(b'data:'):continue
                    raw=line[5:].strip()
                    if raw==b'[DONE]':done=True;break
                    part=json.loads(raw)
                    if part.get('error'):raise ValueError('Errore del modello SSD.')
                    usage=part.get('usage') or usage
                    choices=part.get('choices') or []
                    chunk=(choices[0].get('delta',{}).get('content') or '') if choices else ''
                    if chunk and first is None:first=time.monotonic()
                    self.core.partial+=chunk
                    if len(self.core.partial)>16000:raise ValueError('Output SSD troppo lungo.')
            if self.failure or not done or not self.core.partial.strip():raise ValueError(self.failure or 'Risposta SSD incompleta.')
            self.core.tokens('chat',usage.get('prompt_tokens'),usage.get('completion_tokens'))
            recorded=True
            await self.checkpoint(model,policy,context,'save')
            self.core.event('activity','latency',json.dumps({'model':model,'backend':'llama.cpp-ssd','policy':policy,
                'first_token_ms':round((first-started)*1000) if first else None,
                'total_ms':round((time.monotonic()-started)*1000),'peak':self.peak,'sha256':self.catalog()[model]['sha256']}))
        finally:
            if not recorded:self.core.tokens('chat')
            await self.stop()

    async def cache_probe(self,model):
        metrics={'cache':'persistent-context','backend':'llama.cpp','samples':[]};status='error'
        try:
            await self.start(model,'mapped',1024)
            prompt=await self.template([{'role':'user','content':'Quanto fa 17+25? Rispondi solo con il numero.'}])
            first=await self.completion(prompt,12)
            self.core.tokens('benchmark',first.get('timings',{}).get('prompt_n'),first.get('timings',{}).get('predicted_n'))
            if not await self.checkpoint(model,'mapped',1024,'save','probe'):raise ValueError('Checkpoint non salvato: consulta attività.')
            await self.stop();await self.start(model,'mapped',1024)
            if not await self.checkpoint(model,'mapped',1024,'restore','probe'):raise ValueError('Checkpoint non ripristinato: consulta attività.')
            second=await self.completion(prompt,12)
            self.core.tokens('benchmark',second.get('timings',{}).get('prompt_n'),second.get('timings',{}).get('predicted_n'))
            metrics.update({'samples':[first,second],'same_tokens':bool(first.get('tokens')) and first['tokens']==second.get('tokens'),
                            'same_text':first['content']==second['content'],'peak':dict(self.peak)})
            if not metrics['same_tokens'] or second.get('timings',{}).get('cache_n',0)==0:
                raise ValueError('Cache non riutilizzata o token diversi.')
            status='ok'
        except asyncio.CancelledError:status='interrupted';raise
        except Exception as exc:metrics['error']=str(exc)[:500]
        finally:
            await self.stop()
            self.core.store.execute('INSERT INTO core_benchmarks(model,options,status,metrics,created) VALUES(?,?,?,?,?)',
                (model,json.dumps({'ssd_policy':'cache_probe','ctx':1024,'kv':'f16'}),status,json.dumps(metrics),time.time()))
            self.core.event('activity','ssd_cache_probe',json.dumps({'model':model,'status':status,'metrics':metrics}))

    async def benchmark(self,model):
        await self.unload_ollama()
        prompts=[('python','Scrivi solo la funzione Python unique(values) che rimuove duplicati mantenendo ordine.'),
                 ('logic','Se tre scatole contengono rispettivamente 2, 3 e 5 bulloni, quanti bulloni ci sono in totale? Rispondi brevemente in italiano.'),
                 ('english','Explain in one sentence why putting a neural network on SSD does not make SSD as fast as RAM.')]
        baseline={};placement=self.planning(model)
        output_budget=96
        if placement['classification']=='disk_bound':
            # Oversized dense weights need a bounded, complete probe rather
            # than many minutes of explanatory code per sample.
            output_budget=32
            prompts=[('logic','Quanto fa 17+25? Rispondi solo con il numero.'),
                     ('python','Solo codice: definisci unique(values) su una riga con list(dict.fromkeys(values)). Nessuna spiegazione.'),
                     ('english','In at most six words: is SSD faster than RAM?')]
        # Stable non-repacked target is the token reference, including in the
        # speculative verifier. Repacking changes CPU kernels/rounding and can
        # transiently require a second full copy, not merely a little overhead.
        policies=['mapped']
        if placement['repack_peak_fits']:policies.append('native')
        if placement['classification']=='resident':policies.append('speculative')
        for policy in policies:
            metrics={'cache':'native-runtime','backend':'llama.cpp','plan':placement,'peak':{},'samples':[],
                     'output_budget':output_budget}
            status='error';started=time.monotonic()
            self.core.event('activity','ssd_benchmark_start',json.dumps({'model':model,'policy':policy}))
            try:
                await self.start(model,policy)
                metrics['load_ms']=round((time.monotonic()-started)*1000)
                for topic,query in prompts:
                    prompt=await self.template([{'role':'user','content':query}])
                    for cache in ('cold','warm'):
                        value=await self.completion(prompt,output_budget)
                        timing=value.get('timings',{})
                        sample={'topic':topic,'cache':cache,'content':value.get('content',''),
                                'tokens':value.get('tokens',[]),'wall_ms':value['wall_ms'],'timings':timing,
                                'tokens_per_second':timing.get('predicted_per_second'),
                                'stop_type':value.get('stop_type'),'stopped_limit':value.get('stopped_limit')}
                        if policy==policies[0]:baseline[(topic,cache)]=sample
                        else:
                            reference=baseline[(topic,cache)]
                            sample['same_tokens']=bool(sample['tokens']) and sample['tokens']==reference['tokens']
                            sample['same_text']=sample['content']==reference['content']
                        metrics['samples'].append(sample)
                        self.core.tokens('benchmark',timing.get('prompt_n'),timing.get('predicted_n'))
                warm=[s for s in metrics['samples'] if s['cache']=='warm']
                metrics['tokens_per_second']=round(sum(s['tokens_per_second'] or 0 for s in warm)/len(warm),2)
                metrics['wall_ms']=sum(s['wall_ms'] for s in warm)
                metrics['first_token_ms']=None
                metrics['token_match']=all(s.get('same_tokens',True) for s in metrics['samples'])
                import re
                code=next(s['content'] for s in metrics['samples'] if s['topic']=='python');fenced=re.search(r'```(?:python)?\s*\n(.*?)```',code,re.S)
                rc,result=await self.core.learning.exercise(fenced[1] if fenced else code.strip(),
                    {'function':'unique','cases':[{'args':[[3,1,3,2,1]],'expected':[3,1,2]},
                                                 {'args':[[]],'expected':[]},{'args':[['a','A','a']],'expected':['a','A']}]})
                metrics['test_passed']=rc==0;metrics['test_result']=result[:1800];status='ok'
            except asyncio.CancelledError:status='interrupted';metrics['error']='Interrotto per priorità chat';raise
            except Exception as exc:metrics['error']=self.failure or str(exc)[:500] or type(exc).__name__
            finally:
                metrics['peak']=dict(self.peak);await self.stop()
                self.core.store.execute('INSERT INTO core_benchmarks(model,options,status,metrics,created) VALUES(?,?,?,?,?)',
                    (model,json.dumps({'ssd_policy':policy,'ctx':1024,'kv':'f16'}),status,json.dumps(metrics),time.time()))
                self.core.event('activity','ssd_benchmark_result',json.dumps({'model':model,'policy':policy,'status':status,'metrics':metrics},ensure_ascii=False))
