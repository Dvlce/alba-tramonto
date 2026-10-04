"""One-time local CPU training environment and immutable public model download."""
import argparse
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

BASE_ID = 'Qwen/Qwen2.5-Coder-0.5B-Instruct'
BASE_REVISION = 'ea3f2471cf1b1f0db85067f1ef93848e38e88c25'
TORCH_WHEEL = ('https://download-r2.pytorch.org/whl/cpu/'
    'torch-2.12.1%2Bcpu-cp313-cp313-manylinux_2_28_aarch64.whl'
    '#sha256=8d47e0cfc59679d4e367646c3df4cf433c7d1595b31307e0e7b2391c58ca2160')


def prepare(root):
    if platform.machine() not in ('aarch64','arm64') or sys.version_info[:2]!=(3,13):
        raise ValueError('Il pacchetto CPU verificato richiede ARM64 e Python 3.13.')
    root=Path(root).resolve();root.mkdir(mode=0o700,parents=True,exist_ok=True)
    env={'PATH':'/usr/bin:/bin','LC_ALL':'C.UTF-8','PIP_DISABLE_PIP_VERSION_CHECK':'1',
         'PYTHONNOUSERSITE':'1','HF_HUB_DISABLE_TELEMETRY':'1','HF_HUB_DISABLE_XET':'1',
         'HF_HOME':str(root/'hf-cache'),'PIP_CACHE_DIR':str(root/'pip-cache')}
    python=root/'environment/bin/python'
    if not python.exists():subprocess.run([sys.executable,'-m','venv',str(root/'environment')],env=env,check=True)
    subprocess.run([str(python),'-m','pip','install','--index-url','https://pypi.org/simple','--only-binary=:all:',TORCH_WHEEL,
        'transformers==4.57.1','peft==0.17.1','accelerate==1.10.1','safetensors==0.6.2'],env=env,check=True)
    subprocess.run([str(python),'-c',
        'from huggingface_hub import snapshot_download; import sys; snapshot_download('+repr(BASE_ID)+
        ',revision='+repr(BASE_REVISION)+',local_dir=sys.argv[1],allow_patterns=["*.json","*.safetensors","*.txt","LICENSE"],token=False)',
        str(root/'base')],env=env,check=True)
    try:from .prepare_conversion import prepare as convert
    except ImportError:from prepare_conversion import prepare as convert
    convert(root)
    (root/'ready.json').write_text(json.dumps({'base':BASE_ID,'revision':BASE_REVISION,'torch':'2.12.1+cpu'}))
    print('Ambiente CPU e modello base pronti:',root,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);args=parser.parse_args();prepare(args.root)
