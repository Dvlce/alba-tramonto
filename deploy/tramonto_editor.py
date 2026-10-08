#!/usr/bin/env python3
"""Publish only the verified Tramonto editor files, with file rollback and a health check."""
import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path

BASE={'tramonto.html','tramonto.css','tramonto.js','tramonto-lab.js','tramonto.py','lab.py','spice_worker.py','vendor/manifest.json','tramonto-font.js','vendor/opentype.min.js','vendor/OPENTYPE_LICENSE'}
SLUGS={'book','classic','geometric','hand','humanist','script','slab','typewriter'}
FONT_FILES={f'vendor/fonts/{name}-{subset}.woff2' for name in SLUGS for subset in ('latin','latin-ext')}
LICENSES={'vendor/fonts/'+name for name in ('Caveat-OFL.txt','Kalam-OFL.txt','Lora-OFL.txt','Montserrat-OFL.txt','PlayfairDisplay-OFL.txt','SourceSans3-OFL.txt','RobotoSlab-LICENSE.txt','SpecialElite-LICENSE.txt')}
MATHLIVE_FILES={'vendor/mathlive/fonts/KaTeX_Size4-Regular.woff2', 'vendor/mathlive/fonts/KaTeX_SansSerif-Italic.woff2', 'vendor/mathlive/fonts/KaTeX_Size2-Regular.woff2', 'vendor/mathlive/fonts/KaTeX_Main-BoldItalic.woff2', 'vendor/mathlive/fonts/KaTeX_Main-Regular.woff2', 'vendor/mathlive/fonts/KaTeX_Math-BoldItalic.woff2', 'vendor/mathlive/LICENSE.txt', 'vendor/mathlive/fonts/KaTeX_SansSerif-Regular.woff2', 'vendor/mathlive/fonts/KaTeX_Fraktur-Bold.woff2', 'vendor/mathlive/fonts/KaTeX_Caligraphic-Regular.woff2', 'vendor/mathlive/fonts/KaTeX_SansSerif-Bold.woff2', 'vendor/mathlive/fonts/KaTeX_Math-Italic.woff2', 'vendor/mathlive/fonts/KaTeX_Fraktur-Regular.woff2', 'vendor/mathlive/fonts/KaTeX_AMS-Regular.woff2', 'vendor/mathlive/fonts/KaTeX_Size1-Regular.woff2', 'vendor/mathlive/fonts/KaTeX_Main-Bold.woff2', 'vendor/mathlive/fonts/KaTeX_Script-Regular.woff2', 'vendor/mathlive/fonts/KaTeX_Main-Italic.woff2', 'vendor/mathlive/fonts/KaTeX_Caligraphic-Bold.woff2', 'vendor/mathlive/fonts/KaTeX_Typewriter-Regular.woff2', 'vendor/mathlive/fonts/KaTeX_Size3-Regular.woff2', 'vendor/mathlive/mathlive.min.js', 'vendor/mathlive/mathlive-fonts.css'}
FILES=BASE|FONT_FILES|LICENSES|MATHLIVE_FILES

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def run(*args):subprocess.run(args,check=True)

def deploy(root,archive,backups,check=False):
    root=root.resolve();backups.mkdir(mode=0o700,parents=True,exist_ok=True)
    release=backups/('editor-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S'));release.mkdir(mode=0o700)
    stage=release/'stage';stage.mkdir(mode=0o700)
    with tarfile.open(archive,'r:gz') as package:
        entries=package.getmembers();names=[m.name for m in entries]
        if len(names)!=len(set(names)) or set(names)!=FILES|{'release-manifest.json'}:raise ValueError('Unexpected release files')
        manifest=json.load(package.extractfile('release-manifest.json'))
        if set(manifest['files'])!=FILES:raise ValueError('Unexpected manifest files')
        for name in FILES:
            member=package.getmember(name)
            if not member.isfile() or member.size>2_000_000:raise ValueError('Invalid release member: '+name)
            content=package.extractfile(member).read()
            if hashlib.sha256(content).hexdigest()!=manifest['files'][name]:raise ValueError('Hash mismatch: '+name)
            target=stage/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content);target.chmod(0o644)
        for name,expected in manifest['previous'].items():
            if name not in BASE or digest(root/name)!=expected:raise ValueError('Live file changed since review: '+name)
    for name in FILES:
        if (root/name).is_file():
            backup=release/'previous'/name;backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/name,backup)
    (release/'release-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    if check:print('Validated',len(FILES),'files; staged at',stage);return
    run('systemctl','stop','alba.service')
    try:
        for name in FILES:
            target=root/name;target.parent.mkdir(parents=True,exist_ok=True);os.replace(stage/name,target)
        run('systemctl','start','alba.service')
        # A successful TCP/HTTP startup proves Python imports and route setup.
        import time
        for attempt in range(20):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8088/',timeout=2) as response:
                    if response.status==200:break
            except OSError:
                if attempt==19:raise
                time.sleep(.5)
        for name,expected in manifest['files'].items():
            if digest(root/name)!=expected:raise ValueError('Published hash mismatch: '+name)
    except Exception:
        run('systemctl','stop','alba.service')
        for name in FILES:
            backup=release/'previous'/name
            if backup.is_file():shutil.copy2(backup,root/name)
            elif (root/name).exists():(root/name).unlink()
        run('systemctl','start','alba.service');raise
    print('Published',len(FILES),'Tramonto editor files; rollback copy:',release)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--archive',type=Path,required=True);parser.add_argument('--backups',type=Path,required=True);parser.add_argument('--check',action='store_true');args=parser.parse_args();deploy(args.root,args.archive,args.backups,args.check)
