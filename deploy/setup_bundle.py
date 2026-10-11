"""Verified single-file payload extraction. Never copies configuration or data."""
import base64
import hashlib
import io
import json
import os
import platform
import subprocess
import sys
import tarfile
from pathlib import Path, PurePosixPath


def allowed(name):
    p=PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or not p.parts or any(c in name for c in '\\:\r\n'):return False
    if any(part.startswith('.') for part in p.parts):return False
    if p.parts[0] in ('data','backups','preinstall','artifacts','dist','tests','android','whatsapp'):return False
    if len(p.parts)==1:return p.suffix in ('.py','.html','.css','.js','.txt','.md') or name=='LICENSE'
    if p.parts[0]=='deploy':return name in ('deploy/alba.service','deploy/portable_install.py','deploy/setup_bundle.py')
    return p.parts[0] in ('core','vendor','docs')


def unpack(raw,target):
    target=Path(target).resolve()
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
        members=archive.getmembers()
        if len(members)>2000 or any(not m.isfile() or m.size>20*1024*1024 for m in members):raise ValueError('Invalid setup archive')
        if len({m.name for m in members})!=len(members):raise ValueError('Duplicate archive members')
        manifest=json.load(archive.extractfile('setup-manifest.json'))
        if set(manifest)!=set(m.name for m in members)-{'setup-manifest.json'}:raise ValueError('Invalid setup manifest')
        verified={}
        for name,digest in manifest.items():
            if not allowed(name):raise ValueError('Forbidden setup path: '+name)
            content=archive.extractfile(name).read()
            if hashlib.sha256(content).hexdigest()!=digest:raise ValueError('Setup hash mismatch: '+name)
            destination=target/name
            if not destination.resolve().is_relative_to(target):raise ValueError('Destination escapes setup directory')
            if destination.exists() and destination.read_bytes()!=content:raise ValueError('Existing code differs; use a new installation directory: '+name)
            verified[name]=content
        marker=target/'setup-bundle.sha256';fingerprint=hashlib.sha256(raw).hexdigest()
        if target.exists() and any(target.iterdir()) and (not marker.is_file() or marker.read_text().strip()!=fingerprint):raise ValueError('Choose an empty directory; existing installations are not overwritten.')
        target.mkdir(mode=0o700,parents=True,exist_ok=True)
        # Write first so an interrupted extraction of this identical bundle can resume.
        marker.write_text(fingerprint+'\n');marker.chmod(0o600)
        for name,content in verified.items():
            path=target/name;path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            temporary=path.with_name(path.name+'.setup-tmp');temporary.write_bytes(content);temporary.chmod(0o644);temporary.replace(path)
    return target


def main(expected_hash):
    arguments=sys.argv[2:]
    root=None;extract=False
    for flag in ('--directory','--extract-only'):
        if flag in arguments:
            index=arguments.index(flag)
            if index+1>=len(arguments):raise ValueError(flag+' requires a directory')
            root=Path(arguments[index+1]).expanduser();extract=flag=='--extract-only'
            del arguments[index:index+2]
    if root is None:
        root=Path(os.environ['LOCALAPPDATA'])/'Alba' if platform.system()=='Windows' else Path.home()/('Library/Application Support/Alba' if platform.system()=='Darwin' else 'alba-tramonto')
    source=Path(sys.argv[1]).read_text(encoding='utf-8-sig')
    block=source.rsplit('\n__ALBA_PAYLOAD__\n',1)[-1] if '\n__ALBA_PAYLOAD__\n' in source else source.rsplit('\n# __ALBA_PAYLOAD__\n',1)[-1]
    raw=base64.b64decode(''.join(line.removeprefix('# ').strip() for line in block.splitlines()),validate=True)
    if hashlib.sha256(raw).hexdigest()!=expected_hash:raise ValueError('Damaged setup payload; download again.')
    if '--plan' in arguments:
        print(json.dumps({'system':platform.system(),'directory':str(root),'embedded_payload_sha256':expected_hash,'install_arguments':arguments,'network':'Only dependencies and public model downloads; application sources are embedded.'},indent=2));return
    os.umask(0o077);target=unpack(raw,root)
    print('Verified application bundle extracted to '+str(target),flush=True)
    if not extract:subprocess.run([sys.executable,str(target/'install.py'),*arguments],cwd=target,check=True)


if __name__=='__main__':main(sys.argv[-1])
