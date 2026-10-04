"""Administrative setup for the pinned ARM CPU runtime and read-only GGUFs.

Run on the Pi, never as a web-request installer. Imported models are hard links
when possible, otherwise verified copies; original weights are never modified.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from .prepare_conversion import LLAMA_REVISION


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda:source.read(8*1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def register(root, ollama, model):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*(?:/[A-Za-z0-9][A-Za-z0-9_.-]*)?(?::[A-Za-z0-9][A-Za-z0-9_.-]*)?',model) or '..' in model:
        raise ValueError('Usa il nome di un modello Ollama installato.')
    name,tag = model.rsplit(':',1) if ':' in model else (model,'latest')
    components = name.split('/')
    manifest = ollama/'manifests/registry.ollama.ai'/('library' if len(components)==1 else components[0])/components[-1]/tag
    if not manifest.resolve().is_relative_to(ollama.resolve()): raise ValueError('Manifest esterno.')
    layers=json.loads(manifest.read_text())['layers']
    layer=next(v for v in layers if v['mediaType']=='application/vnd.ollama.image.model')
    expected=layer['digest'].removeprefix('sha256:')
    if not re.fullmatch('[0-9a-f]{64}',expected): raise ValueError('Digest non valido.')
    source=ollama/'blobs'/('sha256-'+expected)
    if source.is_symlink() or not source.is_file(): raise ValueError('Blob non valido.')
    if source.stat().st_size!=layer['size'] or digest(source)!=expected: raise ValueError('Hash del modello non valido.')
    directory=root/'models';directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    target=directory/(expected+'.gguf')
    if not target.exists():
        # Read-only to the service user; linking avoids doubling SSD usage.
        if source.stat().st_mode & 0o004:
            try:os.link(source,target)
            except OSError:shutil.copyfile(source,target)
        else:shutil.copyfile(source,target)
    if digest(target)!=expected:raise ValueError('Verifica copia GGUF fallita.')
    path=root/'models.json'
    models=json.loads(path.read_text()) if path.exists() else {}
    models[model]={'file':target.name,'sha256':expected,'size':target.stat().st_size}
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(models,indent=2)+'\n');temporary.chmod(0o600);temporary.replace(path)
    return models[model]


def build(root, source):
    if not (source/'CMakeLists.txt').is_file():raise ValueError('Prepara prima il convertitore llama.cpp fissato a '+LLAMA_REVISION)
    build_dir=root/'build'
    subprocess.run(['cmake','-S',str(source),'-B',str(build_dir),'-DCMAKE_BUILD_TYPE=Release',
                    '-DGGML_NATIVE=ON','-DGGML_OPENMP=ON','-DLLAMA_CURL=OFF','-DLLAMA_BUILD_TESTS=OFF',
                    '-DLLAMA_BUILD_SERVER=ON','-DBUILD_SHARED_LIBS=OFF'],check=True)
    subprocess.run(['nice','-n','15','cmake','--build',str(build_dir),'--target','llama-server','-j','2'],check=True)
    (root/'build.json').write_text(json.dumps({'revision':LLAMA_REVISION,'native_cpu':True,
                                            'binary_sha256':digest(build_dir/'bin/llama-server')})+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--ollama',type=Path,default=Path('/usr/share/ollama/.ollama/models'))
    parser.add_argument('--model');parser.add_argument('--source',type=Path)
    args=parser.parse_args();args.root.mkdir(mode=0o700,parents=True,exist_ok=True)
    if args.source:build(args.root,args.source)
    if args.model:print(json.dumps(register(args.root,args.ollama,args.model)))
