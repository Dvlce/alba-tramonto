"""Daily local adapter training, traceable versions and conservative promotion."""
import asyncio
import datetime
import json
import os
import re
import shutil
import signal
import time
from pathlib import Path
from zoneinfo import ZoneInfo
from .prepare_training import BASE_ID,BASE_REVISION
from .training_data import examples,HOLDOUT


class Training:
    def __init__(self,core):
        self.core=core;self.root=core.settings.data/'core-training';self.task=None;self.process=None;self.phase='';self.paused=False
        core.store.db.executescript('''CREATE TABLE IF NOT EXISTS core_training(
            id INTEGER PRIMARY KEY,day TEXT NOT NULL,started REAL NOT NULL,finished REAL,
            status TEXT NOT NULL,model TEXT NOT NULL DEFAULT '',dataset_hash TEXT NOT NULL DEFAULT '',
            samples INTEGER NOT NULL DEFAULT 0,metrics TEXT NOT NULL DEFAULT '{}',detail TEXT NOT NULL DEFAULT '');''')
        core.store.execute("UPDATE core_training SET status='interrupted',finished=?,detail='Servizio riavviato durante il ciclo' WHERE status IN ('running','paused','evaluating')",(time.time(),))

    def ready(self):return (self.root/'ready.json').is_file() and (self.root/'environment/bin/python').exists() and (self.root/'llama.cpp/build/bin/llama-quantize').is_file() and bool(shutil.which('bwrap'))
    def today(self):return datetime.datetime.now(ZoneInfo('Europe/Rome'))
    def due(self):
        now=self.today()
        return self.ready() and self.core.config['training_enabled'] and now.hour>=self.core.config['training_hour'] and not self.core.store.rows('SELECT id FROM core_training WHERE day=?',(now.date().isoformat(),))
    def snapshot(self):
        runs=self.core.store.rows('SELECT * FROM core_training ORDER BY id DESC LIMIT 30')
        return {'ready':self.ready(),'running':bool(self.task and not self.task.done()),'phase':self.phase,
                'paused':self.paused,'base':BASE_ID,'base_revision':BASE_REVISION,'active_model':self.core.config['personal_model'],
                'active_adapter':self.core.config['personal_adapter'],'runs':[{**r,'metrics':json.loads(r['metrics'])} for r in runs],
                'schedule':'Europe/Rome · %02d:00'%self.core.config['training_hour']}
    def start(self):
        if self.task and not self.task.done():raise ValueError('Addestramento già in corso.')
        if not self.ready():raise ValueError('Ambiente CPU non ancora preparato.')
        if self.core.settings.backend!='ollama':raise ValueError('Pubblicazione del modello richiede Ollama locale.')
        self.task=asyncio.create_task(self.run())
    async def stop(self):
        if self.task and not self.task.done():self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)

    async def benchmark(self,name):
        cases=[{'function':'cube','cases':[{'args':[3],'expected':27},{'args':[-2],'expected':-8}]},
               {'function':'is_positive','cases':[{'args':[0],'expected':False},{'args':[2],'expected':True}]},
               {'function':'last_or_none','cases':[{'args':[[]],'expected':None},{'args':[[1,2]],'expected':2}]},
               {'function':'maximum','cases':[{'args':[[]],'expected':None},{'args':[[-4,2,1]],'expected':2}]}]
        results=[]
        for (prompt,_),spec in zip(HOLDOUT,cases):
            async with self.core.engine.lock:
                async with self.core.engine.session.post(self.core.settings.llm_url+'/api/chat',json={
                    'model':name,'stream':False,'think':False,'keep_alive':'30s',
                    'messages':[{'role':'system','content':'Scrivi soltanto la funzione Python richiesta, nessuna spiegazione.'},
                                {'role':'user','content':prompt}],
                    'options':{'num_ctx':1024,'num_predict':160,'num_thread':2,'temperature':0}},timeout=180) as response:
                    if response.status!=200:raise ValueError('Benchmark: modello non disponibile.')
                    out=await response.json()
                self.core.tokens('training',out.get('prompt_eval_count'),out.get('eval_count'))
                code=out['message']['content'].strip()
                fenced=re.search(r'```(?:python)?\s*\n(.*?)```',code,re.S)
                if fenced:code=fenced[1]
                rc,output=await self.core.learning.exercise(code,spec)
            results.append({'function':spec['function'],'passed':rc==0,'code':code[:6000],'result':output[:1800]})
            self.core.event('training','benchmark',json.dumps(results[-1],ensure_ascii=False))
        return {'passed':sum(r['passed'] for r in results),'total':len(results),'results':results}

    async def execute(self,work,previous):
        args=['bwrap','--unshare-all','--die-with-parent','--ro-bind','/usr','/usr',
              '--symlink','usr/lib','/lib','--symlink','usr/bin','/bin','--dev','/dev','--ro-bind','/proc','/proc',
              '--tmpfs','/tmp','--dir','/etc','--ro-bind',str(self.root/'environment'),'/venv',
              '--ro-bind',str(self.root/'base'),'/base','--bind',str(work),'/work',
              '--ro-bind',str(Path(__file__).parent/'training_worker.py'),'/worker.py','--chdir','/work']
        if previous and previous.is_dir():args+=['--ro-bind',str(previous),'/previous']
        else:args+=['--dir','/previous']
        if Path('/lib64').exists():args+=['--symlink','usr/lib64','/lib64']
        args+=['/usr/bin/python3','-I','/worker.py']
        env={'PATH':'/usr/bin:/bin','LC_ALL':'C.UTF-8','USER':'alba','HOME':'/tmp',
             'OPENBLAS_NUM_THREADS':'2','OMP_NUM_THREADS':'2'}
        self.process=await asyncio.create_subprocess_exec(*args,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT,
                      env=env,start_new_session=True)
        process=self.process
        async def monitor():
            while process.returncode is None:
                await asyncio.sleep(2)
                # bwrap execs the Python worker as a descendant: measure the whole
                # process group, not just its tiny namespace supervisor.
                rss=0
                for p in Path('/proc').glob('[0-9]*'):
                    try:
                        stat=(p/'stat').read_text().split(') ',1)[1].split()
                        if int(stat[2])!=process.pid:continue
                        match=re.search(r'VmRSS:\s+(\d+)',(p/'status').read_text())
                        if match:rss+=int(match[1])
                    except (OSError,ValueError,IndexError):pass
                if rss>4500*1024:raise ValueError('Training fermato: limite RAM 4,5 GB.')
                r=self.core.resources();pause=self.core.running or self.core.engine.lock.locked() or r['overloaded'] or not self.core.config['enabled'] or self.core.store.setting('bot_paused')=='1'
                if pause!=self.paused:
                    os.killpg(process.pid,signal.SIGSTOP if pause else signal.SIGCONT);self.paused=pause
                    self.core.event('training','pause' if pause else 'resume','Training sospeso per priorità chat/risorse' if pause else 'Training ripreso')
        async def read():
            size=0
            with (work/'training.log').open('w') as log:
                while True:
                    line=await process.stdout.readline()
                    if not line:break
                    size+=len(line)
                    if size>512000:raise ValueError('Log training oltre il limite.')
                    content=line.decode('utf-8',errors='replace');log.write(content);log.flush()
                    try:
                        progress=json.loads(content);self.phase=progress.get('stage','training')
                        self.core.event('training','progress',content[:5000])
                    except json.JSONDecodeError:pass
            return await process.wait()
        watcher=asyncio.create_task(monitor());reader=asyncio.create_task(read())
        try:
            done,_=await asyncio.wait((watcher,reader),timeout=3*3600,return_when=asyncio.FIRST_COMPLETED)
            if not done:raise ValueError('Training interrotto: timeout di tre ore.')
            if watcher in done and watcher.exception():raise watcher.exception()
            return await reader
        finally:
            watcher.cancel();reader.cancel();await asyncio.gather(watcher,reader,return_exceptions=True)
            if process.returncode is None:
                try:
                    if self.paused:os.killpg(process.pid,signal.SIGCONT)
                    os.killpg(process.pid,signal.SIGTERM)
                    await asyncio.wait_for(process.communicate(),10)
                except (ProcessLookupError,asyncio.TimeoutError):
                    try:os.killpg(process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    await process.communicate()
            watcher.cancel();reader.cancel();await asyncio.gather(watcher,reader,return_exceptions=True)
            self.process=None;self.paused=False

    async def run(self):
        cancelled=False
        day=self.today().date().isoformat();row=self.core.store.execute('INSERT INTO core_training(day,started,status) VALUES(?,?,?)',(day,time.time(),'running')).lastrowid
        work=self.root/'runs'/str(row);work.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.core.event('training','start','Fine-tuning CPU locale: '+str(row))
        try:
            # A stopped CPU worker still occupies RAM. Release cached inference
            # weights before loading Torch, instead of waiting forever under load.
            async with self.core.engine.lock:
                async with self.core.engine.session.get(self.core.settings.llm_url+'/api/ps',timeout=15) as response:
                    if response.status!=200:raise ValueError('Inventario modelli residenti non disponibile.')
                    resident=(await response.json()).get('models',[])
                for model in resident:
                    async with self.core.engine.session.post(self.core.settings.llm_url+'/api/generate',json={'model':model['name'],'keep_alive':0},timeout=30) as response:
                        if response.status!=200:raise ValueError('Impossibile liberare la memoria del modello.')
                        await response.read()
                self.core.event('training','memory','Cache di inferenza scaricata prima del worker CPU')
            verified=self.core.store.rows("SELECT * FROM core_diary WHERE status='verified' ORDER BY id DESC LIMIT 100")
            train=examples(verified)
            import hashlib
            digest=hashlib.sha256(json.dumps(train,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            spec={'base':BASE_ID,'revision':BASE_REVISION,'train':train,
                  'validation':[{'prompt':p,'answer':a} for p,a in HOLDOUT],'steps':min(24,len(train))}
            (work/'spec.json').write_text(json.dumps(spec,ensure_ascii=False))
            self.core.store.execute('UPDATE core_training SET dataset_hash=?,samples=? WHERE id=?',(digest,len(train),row))
            previous=self.root/'runs'/self.core.config['personal_adapter']/'adapter' if self.core.config['personal_adapter'] else None
            self.phase='loading';rc=await self.execute(work,previous)
            if rc:raise ValueError('Worker CPU non completato. Consulta il log del ciclo.')
            report=json.loads((work/'report.json').read_text())
            self.core.store.execute('UPDATE core_training SET metrics=? WHERE id=?',(json.dumps(report),row))
            if not report['accepted']:
                self.core.store.execute("UPDATE core_training SET status='rejected',finished=?,detail=? WHERE id=?",(time.time(),'Loss di validazione peggiorata: modello precedente conservato',row));return
            self.phase='importing';name='notte-personal:'+day.replace('-','')+'-'+str(row)
            # New Ollama releases may route safetensors through MLX, which
            # cannot load Qwen2 on Linux. Import a portable CPU GGUF instead.
            env={'PATH':'/usr/local/bin:/usr/bin:/bin','LC_ALL':'C.UTF-8','PYTHONNOUSERSITE':'1',
                 'HOME':str(self.root),'USER':'alba','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','OMP_NUM_THREADS':'2'}
            self.core.event('training','conversion','Conversione e quantizzazione CPU GGUF Q4_K_M')
            source=self.root/'llama.cpp';fp16=work/'candidate-f16.gguf';quantized=work/'candidate-q4.gguf'
            async with self.core.engine.lock:
                rc,out=await self.core.learning.bounded_process([str(self.root/'environment/bin/python'),str(source/'convert_hf_to_gguf.py'),
                    str(work/'merged'),'--outfile',str(fp16),'--outtype','f16'],180,env,output_limit=262144)
                if rc:raise ValueError('Conversione GGUF non riuscita: '+out[-1200:])
                rc,out=await self.core.learning.bounded_process([str(source/'build/bin/llama-quantize'),str(fp16),str(quantized),'Q4_K_M','2'],180,env,output_limit=262144)
                if rc:raise ValueError('Quantizzazione CPU non riuscita: '+out[-1200:])
                (work/'Modelfile').write_text('FROM '+str(quantized)+'\nPARAMETER num_ctx 2048\n')
                rc,out=await self.core.learning.bounded_process(['ollama','create',name,'-f',str(work/'Modelfile')],300,
                       {'PATH':'/usr/local/bin:/usr/bin:/bin','LC_ALL':'C.UTF-8','HOME':str(self.root),'USER':'alba','OLLAMA_HOST':self.core.settings.llm_url},output_limit=262144)
            if rc:raise ValueError('Import Ollama non riuscito: '+out[-1200:])
            report['gguf_sha256']=hashlib.sha256(quantized.read_bytes()).hexdigest()
            self.core.event('training','imported',name+' · '+report['gguf_sha256'])
            shutil.rmtree(work/'merged')
            fp16.unlink();quantized.unlink()
            self.phase='benchmark'
            report['benchmark']=await self.benchmark(name)
            (work/'report.json').write_text(json.dumps(report))
            self.core.store.execute('UPDATE core_training SET metrics=? WHERE id=?',(json.dumps(report),row))
            # Validation loss alone is not proof of correct code. A candidate
            # that fails an independent execution test cannot replace the adapter.
            if report['benchmark']['passed']!=report['benchmark']['total']:
                self.core.store.execute("UPDATE core_training SET status='rejected',model=?,finished=?,detail=? WHERE id=?",
                    (name,time.time(),'Benchmark funzionale incompleto; checkpoint precedente conservato',row))
                self.core.event('training','rejected',name);return
            self.core.config['personal_model']=name;self.core.config['personal_adapter']=str(row);self.core.save()
            self.core.store.execute("UPDATE core_training SET status='ready',model=?,finished=?,detail=? WHERE id=?",
                  (name,time.time(),'LoRA verificato (4/4), disponibile nella chat personale; profilo principale conservato',row))
            self.core.event('training','complete',json.dumps({'model':name,'metrics':report},ensure_ascii=False))
        except asyncio.CancelledError:
            cancelled=True
            self.core.store.execute("UPDATE core_training SET status='interrupted',finished=?,detail='Interrotto dall’amministratore o dal riavvio' WHERE id=?",(time.time(),row))
            self.core.event('training','interrupted','Training interrotto; modello precedente conservato');raise
        except Exception as exc:
            self.core.store.execute("UPDATE core_training SET status='error',finished=?,detail=? WHERE id=?",(time.time(),str(exc)[:1200],row))
            self.core.event('training','error',str(exc)[:1200])
        finally:
            # Keep seven adapters and generated Ollama versions. Small provenance
            # files remain readable for all cycles, including rejected candidates.
            versions=self.core.store.rows("SELECT id,model FROM core_training WHERE model!='' AND status!='expired' ORDER BY id DESC")
            for old in ([] if cancelled else versions[7:]):
                if str(old['id'])==self.core.config['personal_adapter']:continue
                model=old['model']
                if re.fullmatch(r'notte-personal:\d{8}-\d+',model):
                    try:
                        async with self.core.engine.lock:
                            await self.core.learning.bounded_process(['ollama','rm',model],30,{'PATH':'/usr/local/bin:/usr/bin:/bin','OLLAMA_HOST':self.core.settings.llm_url})
                        adapter=self.root/'runs'/str(old['id'])/'adapter'
                        if adapter.is_dir():shutil.rmtree(adapter)
                        self.core.store.execute("UPDATE core_training SET status='expired' WHERE id=?",(old['id'],))
                    except Exception:pass
            # Interrupted or failed conversion must not retain gigabytes per day.
            if (work/'merged').is_dir():shutil.rmtree(work/'merged')
            for path in (work/'candidate-f16.gguf',work/'candidate-q4.gguf'):
                if path.exists():path.unlink()
            self.phase=''

    def files(self,ident):
        if not str(ident).isdigit() or not self.core.store.rows('SELECT id FROM core_training WHERE id=?',(int(ident),)):raise ValueError('Ciclo non valido.')
        work=self.root/'runs'/str(int(ident));result={}
        for name in ('spec.json','report.json','training.log'):
            path=work/name
            if path.is_file():result[name]=path.read_text()[:512000]
        return result
