#!/usr/bin/env python3
"""Deploy a verified release, preserving .env/data and rolling code back on failure.

Run as root on the existing Raspberry installation. No SSH/firewall changes.
"""
import argparse
import datetime
import hashlib
import json
import os
import pwd
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT_FILES = {'app.py','service.py','telegram_bot.py','runtime_features.py','install.py',
              'web.html','web.css','web.js','portal-motion.js','tramonto.html','tramonto.css','tramonto.js',
              'tramonto-lab.js','notte.html','notte.css','notte.js'}


def allowed(name):
    p=Path(name)
    if p.is_absolute() or '..' in p.parts: return False
    return name in ROOT_FILES or (len(p.parts)>1 and p.parts[0] in ('core','vendor','tests','docs','dist')
            and p.suffix in ('.py','.txt','.js','.css','.md','.json','.apk','.woff2','.png'))


def deploy(archive,root,check=False):
    root=root.resolve()
    if not (root/'app.py').is_file() or not (root/'.venv/bin/python').exists(): raise ValueError('Installazione Alba non trovata.')
    with tempfile.TemporaryDirectory(prefix='.core-release-',dir=root) as temporary:
        stage=Path(temporary)
        with tarfile.open(archive,'r:gz') as package:
            members=package.getmembers()
            if len({m.name for m in members})!=len(members) or any(not m.isfile() for m in members): raise ValueError('Archivio non valido.')
            manifest=json.load(package.extractfile('release-manifest.json'))
            if not isinstance(manifest,dict) or set(manifest)!=set(m.name for m in members)-{'release-manifest.json'}: raise ValueError('Manifest non valido.')
            for name,digest in manifest.items():
                if not allowed(name): raise ValueError('File non autorizzato: '+name)
                destination=root/name
                if not destination.resolve().is_relative_to(root): raise ValueError('Percorso esterno.')
                content=package.extractfile(name).read()
                if hashlib.sha256(content).hexdigest()!=digest: raise ValueError('Hash errato: '+name)
                target=stage/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
                if target.suffix=='.py': compile(content,name,'exec')
        print('Release verificata:',len(manifest),'file.')
        if check: return
        if os.geteuid()!=0: raise PermissionError('Serve sudo per backup e riavvio del servizio alba.')
        # Existing application code performs the encrypted online backup before replacement.
        subprocess.run(['runuser','-u','alba','--',str(root/'.venv/bin/python'),'maintenance.py','backup'],cwd=root,check=True)
        stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')
        previous=root/'preinstall'/('core-'+stamp);previous.mkdir(mode=0o700,parents=True)
        existing=[];created=[]
        for name in manifest:
            if (root/name).exists():
                target=previous/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/name,target);existing.append(name)
            else:created.append(name)
        (previous/'manifest.json').write_text(json.dumps({'existing':existing,'created':created},indent=2))
        account=pwd.getpwnam('alba')
        subprocess.run(['systemctl','stop','alba'],check=True)
        try:
            for name in manifest:
                target=root/name;target.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
                shutil.copyfile(stage/name,target);target.chmod(0o644);os.chown(target,0,account.pw_gid)
                if hashlib.sha256(target.read_bytes()).hexdigest()!=manifest[name]: raise ValueError('Verifica pubblicazione fallita.')
            subprocess.run(['systemctl','start','alba'],check=True)
            for _ in range(30):
                try:
                    with urllib.request.urlopen('http://127.0.0.1:8088/health',timeout=2) as response:
                        if response.status==200: break
                except (OSError,ValueError): time.sleep(1)
            else: raise RuntimeError('Alba non risponde dopo il riavvio.')
            if subprocess.run(['systemctl','is-active','--quiet','alba']).returncode: raise RuntimeError('Servizio Alba non attivo.')
        except BaseException:
            subprocess.run(['systemctl','stop','alba'],check=False)
            for name in existing:shutil.copy2(previous/name,root/name)
            for name in created:(root/name).unlink(missing_ok=True)
            subprocess.run(['systemctl','start','alba'],check=False)
            raise
        print('Notte attivata. Copia del codice precedente:',previous)
        print('Database, account, chiavi e quaderni conservati; backup cifrato creato.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('archive',type=Path)
    parser.add_argument('--root',type=Path,default=Path('/home/dvlce/supporto-ai'));parser.add_argument('--check',action='store_true')
    args=parser.parse_args();deploy(args.archive,args.root,args.check)
