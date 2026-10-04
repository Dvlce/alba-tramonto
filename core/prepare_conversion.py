"""Pinned llama.cpp converter and CPU quantizer, independent of Ollama releases."""
import io
import os
import subprocess
import tarfile
import urllib.request
from pathlib import Path

LLAMA_REVISION='dd266785c2595775001c1c714bd9d92b3ef34cde'

def prepare(root):
    root=Path(root).resolve();source=root/'llama.cpp';python=root/'environment/bin/python'
    env={'PATH':'/usr/local/bin:/usr/bin:/bin','LC_ALL':'C.UTF-8','PYTHONNOUSERSITE':'1',
         'PIP_DISABLE_PIP_VERSION_CHECK':'1','PIP_CACHE_DIR':str(root/'pip-cache')}
    if not source.exists():
        with urllib.request.urlopen('https://codeload.github.com/ggml-org/llama.cpp/tar.gz/'+LLAMA_REVISION,timeout=180) as response:raw=response.read(128*1024*1024+1)
        if len(raw)>128*1024*1024:raise ValueError('Archivio convertitore troppo grande.')
        staging=root/'converter-source';staging.mkdir(exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:archive.extractall(staging,filter='data')
        (staging/('llama.cpp-'+LLAMA_REVISION)).rename(source)
    subprocess.run([str(python),'-m','pip','install','--index-url','https://pypi.org/simple','--only-binary=:all:',
                    'sentencepiece==0.2.1','protobuf==6.33.0','numpy','pyyaml'],env=env,check=True)
    subprocess.run([str(python),'-m','pip','install','--index-url','https://pypi.org/simple',str(source/'gguf-py')],env=env,check=True)
    subprocess.run(['cmake','-S',str(source),'-B',str(source/'build'),'-DCMAKE_BUILD_TYPE=Release',
                    '-DBUILD_SHARED_LIBS=OFF','-DLLAMA_CURL=OFF','-DGGML_NATIVE=OFF','-DLLAMA_BUILD_TESTS=OFF'],env=env,check=True)
    subprocess.run(['cmake','--build',str(source/'build'),'--target','llama-quantize','-j','2'],env=env,check=True)
    print('Convertitore e quantizzatore CPU pronti',flush=True)

if __name__=='__main__':
    import sys
    prepare(sys.argv[1])
