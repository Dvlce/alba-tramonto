#!/usr/bin/env python3
"""Publish verified static notebook assets and an APK; retain a private rollback."""
import argparse,datetime,hashlib,json,os,shutil,tarfile,urllib.request
from pathlib import Path

FILES=('tramonto.css','tramonto-font.js','tramonto-lab.js','tramonto.js',
       'dist/alba-albi.apk','dist/SHA256SUMS','tramonto.html')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def deploy(root,archive,backups,check=False):
    root=root.resolve()
    with tarfile.open(archive,'r:gz') as package:
        members=package.getmembers()
        if len(members)!=len(FILES)+1 or {m.name for m in members}!=set(FILES)|{'release-manifest.json'}:
            raise ValueError('Unexpected release entries')
        if not all(m.isfile() for m in members):raise ValueError('Regular files required')
        manifest=json.load(package.extractfile('release-manifest.json'))
        if set(manifest['files'])!=set(FILES) or set(manifest['previous'])!=set(FILES):
            raise ValueError('Invalid manifest paths')
        content={name:package.extractfile(name).read() for name in FILES}
    for name in FILES:
        if digest(root/name)!=manifest['previous'][name]:raise ValueError('Live file changed: '+name)
        if hashlib.sha256(content[name]).hexdigest()!=manifest['files'][name]:raise ValueError('Release hash mismatch: '+name)
    if check:
        print('Verified',len(FILES),'release entries and current server hashes');return
    release=backups.resolve()/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')
    release.mkdir(parents=True,mode=0o700);release.chmod(0o700)
    stage=root/('.workspace-stage-'+release.name);stage.mkdir(mode=0o700)
    original={name:(root/name).stat() for name in FILES}
    published=[]
    try:
        for name in FILES:
            before=release/'previous'/name;before.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/name,before)
            target=stage/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content[name]);os.chmod(target,original[name].st_mode&0o777);os.chown(target,original[name].st_uid,original[name].st_gid)
        (release/'release-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        for name in FILES:
            if digest(root/name)!=manifest['previous'][name]:raise ValueError('Live file changed before publish: '+name)
            os.replace(stage/name,root/name);published.append(name)
        for name in FILES:
            if digest(root/name)!=manifest['files'][name]:raise ValueError('Published file mismatch: '+name)
        with urllib.request.urlopen('http://127.0.0.1:8088/',timeout=5) as response:
            if response.status!=200:raise ValueError('Health check failed')
        with urllib.request.urlopen('http://127.0.0.1:8088/download/alba-albi.apk',timeout=10) as response:
            if hashlib.sha256(response.read()).hexdigest()!=manifest['files']['dist/alba-albi.apk']:
                raise ValueError('Downloaded APK mismatch')
        print('Published',len(FILES),'files. HTTP 200 and downloaded APK hash verified.')
        print('Private rollback:',release)
        print('Service remained running; notebook data was not modified.')
    except Exception:
        for name in reversed(published):
            target=stage/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(release/'previous'/name,target);os.chown(target,original[name].st_uid,original[name].st_gid);os.replace(target,root/name)
        raise
    finally:shutil.rmtree(stage,ignore_errors=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--archive',type=Path,required=True);parser.add_argument('--backups',type=Path,required=True);parser.add_argument('--check',action='store_true')
    args=parser.parse_args();deploy(args.root,args.archive,args.backups,args.check)
