#!/usr/bin/env python3
"""Build reproducible one-file installers with public, tracked application sources."""
import argparse
import base64
import gzip
import hashlib
import io
import json
import shlex
import subprocess
import tarfile
import textwrap
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PYTHON_VERSION='3.13.16'
MAC_HASH='30666509020b4da0dd8bc2e773255f34d76b7bb80b66960a928d5f6daa0192d7'
WIN_HASH='fb4f9f5d438b2396da0086dc70b935c530cb578e37adc6d354f7ad2037fee83b'
ARM_HASH='696e2226062c6ec3622c13f143d28336a856968518e49cb4f4c62513215a4f5d'


def payload():
    import sys
    sys.path.insert(0,str(ROOT));from deploy.setup_bundle import allowed
    names=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    paths=sorted({n for n in names if n and allowed(n) and (ROOT/n).is_file()})
    for name in paths:
        if (ROOT/name).is_symlink():raise ValueError('Symlink in setup source: '+name)
    manifest={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in paths}
    content=io.BytesIO()
    with tarfile.open(fileobj=content,mode='w',format=tarfile.USTAR_FORMAT) as tar:
        files={n:(ROOT/n).read_bytes() for n in paths};files['setup-manifest.json']=json.dumps(manifest,sort_keys=True).encode()
        for name,data in sorted(files.items()):
            info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644;info.mtime=0;tar.addfile(info,io.BytesIO(data))
    return gzip.compress(content.getvalue(),mtime=0)


def build(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    raw=payload();digest=hashlib.sha256(raw).hexdigest();encoded='\n'.join(textwrap.wrap(base64.b64encode(raw).decode(),76))
    extractor=(ROOT/'deploy/setup_bundle.py').read_text().rsplit("if __name__=='__main__':",1)[0]+f'\nmain({digest!r})\n'
    preamble='''#!/bin/sh
set -eu
case "${1:-}" in --help|-h) printf '%s\\n' 'Alba one-file setup: --directory PATH --plan --skip-system --no-model --no-service --unattended --with-training (Linux)' ; exit 0;; esac
alba_python=''
alba_min_python=10
for argument in "$@"; do case "$argument" in --plan|--extract-only) alba_min_python=9;; esac; done
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys;sys.exit(sys.version_info<(3,int(sys.argv[1])))' "$alba_min_python" >/dev/null 2>&1; then alba_python=$(command -v "$candidate"); break; fi
done
if [ -z "$alba_python" ] && [ "$alba_min_python" -eq 9 ]; then printf '%s\\n' 'Plan: bootstrap Python 3.13, verify/extract embedded sources, install dependencies and Ollama, configure the portal and autostart. No files changed.'; exit 0; fi
'''
    linux=preamble+'''if [ "$(uname -s)" != Linux ]; then printf '%s\\n' 'Use the macOS or Windows setup on this system.'; exit 1; fi
if [ -z "$alba_python" ]; then
  if ! command -v apt-get >/dev/null 2>&1; then printf '%s\\n' 'Install Python 3.10+ and run again.'; exit 1; fi
  if [ "$(id -u)" -eq 0 ]; then apt-get update; apt-get install -y python3 python3-venv ca-certificates; else sudo apt-get update; sudo apt-get install -y python3 python3-venv ca-certificates; fi
  alba_python=$(command -v python3)
fi
'''
    mac=preamble+f'''if [ "$(uname -s)" != Darwin ]; then printf '%s\\n' 'Use the Linux or Windows setup on this system.'; exit 1; fi
if [ -z "$alba_python" ]; then
  alba_temp=$(mktemp -d); trap 'rm -rf "$alba_temp"' EXIT HUP INT TERM
  curl --fail --location --proto '=https' --tlsv1.2 'https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-macos11.pkg' -o "$alba_temp/python.pkg"
  printf '%s  %s\\n' '{MAC_HASH}' "$alba_temp/python.pkg" | shasum -a 256 -c -
  sudo /usr/sbin/installer -pkg "$alba_temp/python.pkg" -target /
  '/Applications/Python 3.13/Install Certificates.command'
  alba_python='/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13'
fi
'''
    for name,script in [('alba-setup-linux.sh',linux),('alba-setup-macos.command',mac)]:
        path=output/name;path.write_text(script+'"$alba_python" -c '+shlex.quote(extractor)+' "$0" "$@"\nexit 0\n__ALBA_PAYLOAD__\n'+encoded+'\n');path.chmod(0o755)
    windows=f'''# Alba one-file setup. Run as the installing user, not as Administrator.
$SetupArguments=@($args)
$ErrorActionPreference='Stop'
if ($SetupArguments -contains '--help') {{Write-Output 'Alba setup: --directory PATH --plan --skip-system --no-model --no-service --unattended';exit 0}}
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
$albaPython=$null
foreach ($candidate in @((Join-Path $env:LOCALAPPDATA 'Programs\\Python\\Python313\\python.exe'),'python.exe','python3.exe')) {{
  $command=Get-Command $candidate -ErrorAction SilentlyContinue
  if ($command -and $command.Source -notmatch 'WindowsApps') {{
    & $command.Source -c 'import sys;sys.exit(sys.version_info<(3,10))' 2>$null
    if ($LASTEXITCODE -eq 0) {{$albaPython=$command.Source;break}}
  }}
}}
if (-not $albaPython) {{
  $arm=$env:PROCESSOR_ARCHITECTURE -eq 'ARM64'
  $arch=if ($arm) {{'arm64'}} else {{'amd64'}}
  $hash=if ($arm) {{'{ARM_HASH}'}} else {{'{WIN_HASH}'}}
  $temp=Join-Path $env:TEMP ('alba-python-'+[guid]::NewGuid().ToString()+'.exe')
  try {{
    Invoke-WebRequest -UseBasicParsing -Uri "https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-$arch.exe" -OutFile $temp
    if ((Get-FileHash $temp -Algorithm SHA256).Hash.ToLowerInvariant() -ne $hash) {{throw 'Python installer checksum failed'}}
    $process=Start-Process -FilePath $temp -ArgumentList '/quiet InstallAllUsers=0 PrependPath=1 Include_test=0' -Wait -PassThru
    if ($process.ExitCode -ne 0) {{throw 'Python installation failed'}}
  }} finally {{Remove-Item $temp -Force -ErrorAction SilentlyContinue}}
  $albaPython=Join-Path $env:LOCALAPPDATA 'Programs\\Python\\Python313\\python.exe'
}}
$code=@'
{extractor}
'@
$helper=Join-Path $env:TEMP ('alba-bundle-'+[guid]::NewGuid().ToString()+'.py')
try {{
  [IO.File]::WriteAllText($helper,$code,[Text.UTF8Encoding]::new($false))
  & $albaPython $helper $PSCommandPath @SetupArguments
  $albaExit=$LASTEXITCODE
}} finally {{Remove-Item $helper -Force -ErrorAction SilentlyContinue}}
if ($albaExit -ne 0) {{exit $albaExit}}
# __ALBA_PAYLOAD__
'''
    (output/'alba-setup-windows.ps1').write_text(windows+'\n'.join('# '+line for line in encoded.splitlines())+'\n',encoding='utf-8-sig')
    files=sorted(p for p in output.iterdir() if p.suffix in ('.sh','.command','.ps1'))
    (output/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in files))
    print(json.dumps({'files':[p.name for p in files],'payload_bytes':len(raw),'payload_sha256':digest},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'dist/setup');args=parser.parse_args();build(args.output)
