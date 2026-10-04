"""Explicit operator-run public probe campaign; models run only on the Pi.

Uses the private Lab API/lock. Never exports other lab rows or personal context.
"""
import argparse,asyncio,datetime,json,re,sys,time
from pathlib import Path
from types import SimpleNamespace
from aiohttp import ClientSession
from config import Settings
from store import Store
from security import Keys,secret_file
from .learning import Learning

NAMES={'mapped':'Notte SSD','native':'Notte ARM','compact':'Notte KV8','speculative':'Notte Draft','warm':'Notte Warm','cpu2':'Notte CPU2','adaptive':'Notte Flux'}
CODE='Scrivi solo la funzione Python unique(values): rimuovi duplicati mantenendo ordine. Nessuna spiegazione.'
LONG=('Riferimento pubblico sintetico per misurare un input lungo: '+('dato=17; altro=25; la risposta va alla fine. '*34)+'\nQuanto fa 17+25? Rispondi solo con il numero.')
SPEC={'function':'unique','cases':[{'args':[[3,1,3,2,1]],'expected':[3,1,2]},{'args':[[]],'expected':[]},{'args':[['a','A','a']],'expected':['a','A']}]}

async def campaign(root,output,model):
 settings=Settings.from_env(root);store=Store(settings.data/'alba.sqlite3');keys=Keys(store,secret_file(settings.data/'auth.key'));owner=settings.admins[0] if settings.admins else int(store.setting('bootstrap_admin','0'));cookie,csrf=keys.create_session(owner,False)
 folder=settings.data/'core-lab-campaign';folder.mkdir(mode=0o700,parents=True,exist_ok=True)
 probes=Store(folder/'checks.sqlite3');learning=Learning(SimpleNamespace(settings=SimpleNamespace(data=folder),store=probes))
 saved=None;results=[];started=time.time();document={'date':datetime.datetime.now(datetime.timezone.utc).isoformat(),'model':model,'hardware':'Raspberry Pi 5 / 8 GB / NVMe / CPU','protocol':'Sequential standard first then selected policy. One repetition per condition. Startup included, OS file cache not evicted; warm and CPU2 benefit from the preceding standard request. Flux changes instructions/budgets; KV8 quantizes KV. No personal context. No model substitution.','results':results}
 def save():output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(document,ensure_ascii=False,indent=2)+'\n')
 try:
  async with ClientSession(trust_env=False) as session:
   headers={'Cookie':'session='+cookie,'X-CSRF-Token':csrf}
   async def call(path,body=None):
    async with session.request('POST' if body is not None else 'GET','http://127.0.0.1:'+str(settings.web_port)+path,headers=headers,json=body) as response:
     value=await response.json()
     if response.status>=300:raise ValueError(value.get('error','HTTP '+str(response.status)))
     return value
   state=await call('/api/notte/status')
   if state['training']['running']:raise ValueError('Training attivo: campagna rinviata senza interromperlo.')
   saved={k:state['config'][k] for k in ('enabled','study_enabled','reddit_enabled','training_enabled')}
   await call('/api/notte/action',{'action':'config','config':{k:False for k in saved}})
   if state['running'] and state['mode'] not in ('chat','personal_chat'):await call('/api/notte/action',{'action':'stop'})
   if state['running'] and state['mode'] in ('chat','personal_chat'):raise ValueError('Chat attiva: rinviare i benchmark.')
   jobs=[('coding',policy,CODE,1024,96) for policy in NAMES]
   jobs.extend(('long_wait',policy,LONG,2048,48) for policy in ('mapped','warm','adaptive'))
   for topic,policy,prompt,context,limit in jobs:
    entry={'topic':topic,'technology':NAMES[policy],'policy':policy,'status':'pending','samples':[]};results.append(entry);save()
    print('START '+topic+' '+NAMES[policy],flush=True)
    try:
     previous=(await call('/api/notte/lab'))['runs'];last=previous[0]['id'] if previous else 0
     config={'model':model,'prompt':prompt,'mode':'compare','policy':policy,'context':context,'output':limit}
     await call('/api/notte/lab',config)
     for _ in range(420):
      await asyncio.sleep(2);runs=(await call('/api/notte/lab'))['runs']
      run=next((r for r in runs if r['id']>last and r['config']==config),None)
      if run and run['status']!='running':break
     else:raise ValueError('Deadline campagna oltre 14 minuti per confronto')
     entry.update(status=run['status'],config=config,weights_sha256=run['result']['weights_sha256'],conditions=run['result']['conditions'],elapsed_ms=round((run['finished']-run['created'])*1000))
     for sample in run['result']['samples']:
      # Explicitly curate only our public probe and non-identifying metrics.
      retained={k:v for k,v in sample.items() if k in ('backend','model','content','status','error','first_token_ms','wall_ms','tokens_per_second','prompt_tokens','output_tokens','load_ms','timings','policy','sha256','peak','generation','output_limit_reached')}
      if topic=='coding' and sample.get('status')=='ok':
       fenced=re.search(r'```(?:python)?\s*\n(.*?)```',sample['content'],re.S);code=fenced[1] if fenced else sample['content'].strip()
       rc,checked=await learning.exercise(code,SPEC);retained['function_check']={'passed':rc==0,'cases':3,'output':checked[:1200]}
      elif topic=='long_wait' and sample.get('status')=='ok':retained['arithmetic_check']={'passed':sample['content'].strip()=='42'}
      entry['samples'].append(retained)
     print('DONE '+json.dumps({'topic':topic,'policy':policy,'status':entry['status'],'samples':[{k:s.get(k) for k in ('backend','first_token_ms','wall_ms','tokens_per_second','output_tokens','error')} for s in entry['samples']]}),flush=True)
    except Exception as exc:entry.update(status='error',error=str(exc)[:500]);print('FAILED '+policy+' '+str(exc)[:200],flush=True)
    finally:save()
   document['elapsed_seconds']=round(time.time()-started);save()
 finally:
  if saved:
   async with ClientSession(trust_env=False) as session:
    async with session.post('http://127.0.0.1:'+str(settings.web_port)+'/api/notte/action',headers={'Cookie':'session='+cookie,'X-CSRF-Token':csrf},json={'action':'config','config':saved}) as response:assert response.status==200,'Restore background flags failed'
  store.execute('DELETE FROM web_sessions WHERE digest=?',(keys.digest(cookie),));store.close();probes.close()
  print('RESTORED background configuration; public report saved at '+str(output),flush=True)

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--model',default='qwen2.5-coder:7b');args=parser.parse_args();asyncio.run(campaign(args.root,args.output,args.model))
