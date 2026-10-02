#!/usr/bin/env python3
"""Publish only Alba's three static files with verified hashes and rollback copies."""
import argparse,datetime,hashlib,json,os,shutil,tarfile
from pathlib import Path

FILES=('web.css','web.js','web.html')

def deploy(root,archive,backups):
    root=root.resolve();backups.mkdir(mode=0o700,parents=True,exist_ok=True)
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')
    release=backups/('alba-'+stamp);release.mkdir(mode=0o700)
    stage=root/('.alba-stage-'+stamp);stage.mkdir(mode=0o755)
    with tarfile.open(archive,'r:gz') as package:
        members=package.getmembers();names=[m.name for m in members]
        if len(names)!=len(set(names)) or set(names)!=set(FILES)|{'release-manifest.json'} or any(not m.isfile() for m in members):raise ValueError('Unexpected release files')
        manifest=json.load(package.extractfile('release-manifest.json'))
        if set(manifest)!=set(FILES):raise ValueError('Unexpected manifest')
        for name in FILES:
            content=package.extractfile(name).read()
            if hashlib.sha256(content).hexdigest()!=manifest[name]:raise ValueError('Release hash mismatch: '+name)
            target=stage/name;target.write_bytes(content);target.chmod(0o644)
    for name in FILES:shutil.copy2(root/name,release/name)
    published=[]
    try:
        for name in FILES:
            os.replace(stage/name,root/name);published.append(name)
        for name in FILES:
            if hashlib.sha256((root/name).read_bytes()).hexdigest()!=manifest[name]:raise ValueError('Published hash mismatch: '+name)
    except Exception:
        for name in published:
            target=stage/name;shutil.copy2(release/name,target);os.replace(target,root/name)
        raise
    (release/'release-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Published Alba HTML/CSS/JS; backup:',release)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('archive',type=Path);parser.add_argument('--root',required=True,type=Path);parser.add_argument('--backups',required=True,type=Path)
    args=parser.parse_args();deploy(args.root,args.archive,args.backups)
