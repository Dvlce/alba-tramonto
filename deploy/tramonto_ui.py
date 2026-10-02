#!/usr/bin/env python3
"""Deploy only Tramonto static files and the signed APK, keeping a private rollback copy."""
import argparse
import datetime
import hashlib
import json
import os
import shutil
import tarfile
from pathlib import Path

FILES = (
    'vendor/html2canvas.min.js', 'vendor/html2canvas-pseudo.css',
    'vendor/HTML2CANVAS_LICENSE', 'vendor/manifest.json',
    'vendor/tramonto-icons.js', 'vendor/LUCIDE_LICENSE',
    'tramonto.css', 'tramonto.js', 'tramonto-lab.js', 'tramonto.html',
    'dist/alba-albi.apk', 'dist/SHA256SUMS',
)

def deploy(root, archive, backups):
    root=root.resolve();backups.mkdir(mode=0o700,parents=True,exist_ok=True)
    release=backups/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')
    release.mkdir(mode=0o700)
    stage=root/('.tramonto-stage-'+release.name);stage.mkdir(mode=0o755)
    with tarfile.open(archive,'r:gz') as package:
        names=[member.name for member in package.getmembers()]
        if len(names)!=len(set(names)) or set(names)!=set(FILES)|{'release-manifest.json'}:
            raise ValueError('Unexpected release files')
        manifest=json.load(package.extractfile('release-manifest.json'))
        for name in FILES:
            member=package.getmember(name)
            if not member.isfile():raise ValueError('Release entries must be regular files')
            content=package.extractfile(member).read()
            if hashlib.sha256(content).hexdigest()!=manifest[name]:raise ValueError('Release hash mismatch: '+name)
            target=stage/name;target.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
            target.write_bytes(content);target.chmod(0o644)
    # All validation and backup reads finish before publishing any file.
    for name in FILES:
        source=root/name
        if source.is_file():
            target=release/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    for name in FILES:
        if name.startswith('dist/'):continue
        os.replace(stage/name,root/name)
    # Keep the renamed root-owned directory in its original parent: changing its
    # parent requires write permission on the directory itself on Linux.
    # The private rollback copy above already contains its APK.
    old_dist=root/('.tramonto-previous-dist-'+release.name)
    if (root/'dist').exists():os.rename(root/'dist',old_dist)
    try:os.rename(stage/'dist',root/'dist')
    except Exception:
        if old_dist.exists():os.rename(old_dist,root/'dist')
        raise
    for name in FILES:
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=manifest[name]:raise ValueError('Published hash mismatch: '+name)
    (release/'release-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Published',len(FILES),'files; backup:',release)
    print('APK SHA256:',manifest['dist/alba-albi.apk'])

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('archive',type=Path);parser.add_argument('--root',required=True,type=Path);parser.add_argument('--backups',required=True,type=Path)
    args=parser.parse_args();deploy(args.root,args.archive,args.backups)
