"""Local administrative client for Notte's authenticated SSD runtime API."""
import argparse
import asyncio
import json
import time
from urllib.parse import urlencode
from aiohttp import ClientSession
from config import Settings
from security import Keys,secret_file
from store import Store


async def main(args):
    settings=Settings.from_env(args.root)
    store=Store(settings.data/'alba.sqlite3')
    keys=Keys(store,secret_file(settings.data/'auth.key'))
    owner=settings.admins[0] if settings.admins else int(store.setting('bootstrap_admin','0'))
    if not owner:store.close();raise ValueError('Amministratore non configurato.')
    cookie,csrf=keys.create_session(owner,False)
    headers={'Cookie':'session='+cookie,'X-CSRF-Token':csrf}
    base='http://127.0.0.1:'+str(settings.web_port)
    try:
        async with ClientSession(trust_env=False,headers=headers) as session:
            async def request(method,path,body=None):
                async with session.request(method,base+path,json=body,timeout=15) as response:
                    value=await response.json()
                    if response.status>=400:raise ValueError(value.get('error','HTTP '+str(response.status)))
                    return value
            if args.command=='plan':
                print(json.dumps(await request('GET','/api/notte/ssd-plan?'+urlencode({'model':args.model,'context':args.context})),indent=2));return
            if args.command=='enable':
                await request('POST','/api/notte/action',{'action':'config','config':{
                    'ssd_enabled':True,'ssd_policy':args.policy,'profile':'advanced','advanced_code_model':args.model}})
                print('Native advanced chat uses exactly '+args.model+'; no automatic smaller-model fallback.');return
            if args.command=='disable':
                await request('POST','/api/notte/action',{'action':'config','config':{'ssd_enabled':False}})
                print('Ollama restored; selected model and stored memory preserved.');return
            before=await request('GET','/api/notte/status')
            wait_started=time.monotonic()
            while before['running'] or before['resources']['model_busy'] or before['training']['running']:
                if time.monotonic()-wait_started>300:raise ValueError('Modello impegnato per oltre cinque minuti; riprova quando è libero.')
                await asyncio.sleep(1)
                before=await request('GET','/api/notte/status')
            cursor=max((r['id'] for r in before['benchmarks']),default=0)
            await request('POST','/api/notte/action',{'action':'ssd_benchmark','text':args.model})
            started=time.monotonic()
            while time.monotonic()-started<1800:
                await asyncio.sleep(2)
                state=await request('GET','/api/notte/status')
                if not state['running'] and state['mode'] is None:
                    rows=[r for r in state['benchmarks'] if r['id']>cursor and r['model']==args.model and 'ssd_policy' in r['options']]
                    print(json.dumps({'error':state['error'],'results':rows},indent=2))
                    if state['error'] or not rows or any(r['status']!='ok' for r in rows):raise ValueError('Benchmark incompleto; consulta risultati e attività.')
                    return
            raise ValueError('Attesa oltre 30 minuti; il ciclo resta visibile e interrompibile nell’app.')
    finally:
        store.execute('DELETE FROM web_sessions WHERE digest=?',(keys.digest(cookie),));store.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('plan','bench','enable','disable'))
    parser.add_argument('--root',default='/home/dvlce/supporto-ai');parser.add_argument('--model',default='qwen2.5-coder:7b')
    parser.add_argument('--context',type=int,default=1024);parser.add_argument('--policy',choices=('auto','native','mapped','speculative'),default='auto')
    asyncio.run(main(parser.parse_args()))
