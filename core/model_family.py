"""Administrative same-weight aliases and explicit project model cleanup on Pi.

No web-request downloader. Stop Alba first; this command never sends messages.
"""
import argparse
import asyncio
import datetime
import hashlib
import json
import os
import re
import shutil
import urllib.request
from pathlib import Path

FAMILY={'notte:latest':'qwen2.5:1.5b','notte-coding:latest':'qwen2.5-coder:7b'}


def api(url,path,body=None,method=None):
    raw=json.dumps(body).encode() if body is not None else None
    request=urllib.request.Request(url+path,data=raw,method=method,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=60) as response:
        data=response.read();return json.loads(data) if data else {}


def weight_id(url,name):
    value=api(url,'/api/show',{'model':name})
    match=re.search(r'^FROM\s+.*sha256[-:]([a-f0-9]{64})\s*$',value.get('modelfile',''),re.M)
    if not match:raise ValueError('Identità GGUF non verificabile: '+name)
    return match[1]


def create_family(settings):
    url=settings.llm_url;inventory={m['name'] for m in api(url,'/api/tags')['models']}
    identities={}
    for destination,source in FAMILY.items():
        chosen=source if source in inventory else destination
        original=weight_id(url,chosen)
        if chosen!=destination:api(url,'/api/copy',{'source':chosen,'destination':destination})
        if weight_id(url,destination)!=original:raise ValueError('Alias con pesi differenti')
        identities[destination]={'source':source,'sha256':original}
    return identities


async def clean_family(settings,store):
    from aiohttp import ClientSession
    from engine import Engine
    from security import Keys,secret_file
    from backups import Backups
    from service import Service
    from .prepare_ssd import register
    config=json.loads(store.setting('core_config','{}'))
    config.update(model='notte:latest',chat_model='notte:latest',code_model='notte-coding:latest',advanced_code_model='notte-coding:latest')
    store.set_setting('core_config',json.dumps(config))
    async with ClientSession(trust_env=False) as session:
        keys=Keys(store,secret_file(settings.data/'auth.key'))
        service=Service(store,settings,keys,Engine(store,settings,session),Backups(store,settings))
        if not getattr(service,'core',None):
            from .runtime import Core
            service.core=Core(service)
        await service.core.training.prune_versions()
        current=service.core.config['personal_adapter'];previous=service.core.config.get('personal_previous_adapter','')
        retained={r['model'] for r in store.rows('SELECT id,model FROM core_training') if str(r['id']) in (current,previous) and r['model']}
        keep=set(FAMILY)|retained|{service.core.config['embedding_model'],service.core.config['embedding_model']+':latest'}
    # Shared base blobs survive because Ollama aliases retain their references.
    removed=[]
    for model in api(settings.llm_url,'/api/tags')['models']:
        if model['name'] not in keep:
            api(settings.llm_url,'/api/delete',{'model':model['name']},'DELETE');removed.append(model['name'])
    inference=settings.data/'core-inference';catalog=inference/'models.json'
    if catalog.is_file():
        models=json.loads(catalog.read_text())
        # The draft is an internal verified-speculation resource, not a chat model.
        allowed=set(FAMILY)|{'qwen2.5-coder:0.5b'}
        selected={name:value for name,value in models.items() if name in allowed}
        old_files={v['file'] for v in models.values()}-{v['file'] for v in selected.values()}
        temporary=catalog.with_suffix('.tmp');temporary.write_text(json.dumps(selected,indent=2)+'\n');temporary.chmod(0o600);temporary.replace(catalog)
        for name in old_files:
            if re.fullmatch(r'[a-f0-9]{64}\.gguf',name):
                (inference/'models'/name).unlink(missing_ok=True)
                for checkpoint in (inference/'kv-cache').glob(name[:-5]+'-*.bin'):checkpoint.unlink()
    return {'retained':sorted(keep),'removed':removed}


def configure_env(root):
    path=root/'.env';lines=path.read_text().splitlines();updates={'MODEL':'notte:latest','CORE_MODEL':'notte:latest','CORE_CHAT_MODEL':'notte:latest','CORE_CODE_MODEL':'notte-coding:latest'}
    result=[];written=set()
    for line in lines:
        key=line.split('=',1)[0].strip()
        if key in updates:
            if key not in written:result.append(key+'='+updates[key]);written.add(key)
        else:result.append(line)
    result.extend(k+'='+v for k,v in updates.items() if k not in written)
    temp=path.with_suffix('.model-update');temp.write_text('\n'.join(result)+'\n');temp.chmod(path.stat().st_mode & 0o777)
    os.chown(temp,path.stat().st_uid,path.stat().st_gid);temp.replace(path)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--clean',action='store_true');args=parser.parse_args()
    if os.geteuid()!=0:raise PermissionError('Esegui come amministratore sul Raspberry; ferma Alba prima della pulizia.')
    from config import Settings
    from store import Store
    settings=Settings.from_env(args.root);identities=create_family(settings)
    from .prepare_ssd import register
    model_dir=Path('/usr/share/ollama/.ollama/models');inference=settings.data/'core-inference'
    for destination in FAMILY:register(inference,model_dir,destination)
    report={'identities':identities}
    if args.clean:
        import subprocess
        if subprocess.run(['systemctl','is-active','--quiet','alba']).returncode==0:raise ValueError('Ferma Alba prima della pulizia.')
        store=Store(settings.data/'alba.sqlite3')
        try:report['cleanup']=asyncio.run(clean_family(settings,store));configure_env(args.root)
        finally:store.close()
    directory=settings.data/'core-models';directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    for folder in (inference,inference/'models',directory):shutil.chown(folder,user='alba',group='alba')
    for file in (inference/'models.json',):shutil.chown(file,user='alba',group='alba')
    path=directory/('family-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')+'.json');path.write_text(json.dumps(report,indent=2)+'\n');path.chmod(0o600);shutil.chown(path,user='alba',group='alba')
    print(json.dumps(report))


if __name__=='__main__':main()
