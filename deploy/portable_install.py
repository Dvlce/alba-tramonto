"""Install the bundled portale on Linux, Windows and macOS. No secrets in argv."""
import argparse
import getpass
import json
import os
import platform
import plistlib
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import venv
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SYSTEM=platform.system()


def run(args,**kwargs):
    return subprocess.run([str(x) for x in args],check=True,**kwargs)


def python_path(root):
    return root/('.venv/Scripts/python.exe' if SYSTEM=='Windows' else '.venv/bin/python')


def download(url,path):
    with urllib.request.urlopen(url,timeout=120) as source,path.open('wb') as target:
        shutil.copyfileobj(source,target)


def ram_bytes():
    if SYSTEM=='Linux':
        return int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemTotal:')))*1024
    if SYSTEM=='Darwin':
        return int(subprocess.check_output(['sysctl','-n','hw.memsize'],text=True))
    import ctypes
    class Memory(ctypes.Structure):
        _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ('physical','available','page','page_available','virtual','virtual_available','extended')]
    value=Memory();value.length=ctypes.sizeof(value)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):raise OSError('Cannot inspect RAM')
    return value.physical


def system_packages(training=False):
    if SYSTEM!='Linux':return
    if not shutil.which('apt-get'):raise ValueError('Automatic dependencies require Debian/Ubuntu/Raspberry Pi OS; otherwise use --skip-system after installing Python, curl, ngspice and bubblewrap.')
    prefix=[] if os.geteuid()==0 else ['sudo']
    run(prefix+['apt-get','update'])
    packages=['python3-venv','python3-pip','curl','ca-certificates','ngspice','bubblewrap']
    if training:packages+=['cmake','g++','make']
    run(prefix+['apt-get','install','-y']+packages)


def find_ollama():
    candidates=[shutil.which('ollama')]
    if SYSTEM=='Darwin':candidates += [str(base/'Ollama.app/Contents/Resources/ollama') for base in (Path('/Applications'),Path.home()/'Applications')]
    if SYSTEM=='Windows':candidates += [str(Path(os.environ.get('LOCALAPPDATA',''))/'Programs/Ollama/ollama.exe')]
    return next((Path(p) for p in candidates if p and Path(p).is_file()),None)


def ollama_ready():
    try:
        with urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=2) as response:return response.status==200
    except OSError:return False


def install_ollama(skip=False):
    binary=find_ollama()
    if binary is None and skip:raise ValueError('Ollama is missing; install it or omit --skip-system.')
    if binary is None:
        with tempfile.TemporaryDirectory(prefix='alba-ollama-') as directory:
            temp=Path(directory)
            if SYSTEM=='Linux':
                script=temp/'install.sh';download('https://ollama.com/install.sh',script);run(['sh',script])
            elif SYSTEM=='Darwin':
                archive=temp/'Ollama.zip';download('https://ollama.com/download/Ollama-darwin.zip',archive)
                apps=Path.home()/'Applications';apps.mkdir(exist_ok=True);run(['ditto','-xk',archive,apps]);run(['open','-a',apps/'Ollama.app'])
            else:
                installer=temp/'OllamaSetup.exe';download('https://ollama.com/download/OllamaSetup.exe',installer);run([installer,'/VERYSILENT','/NORESTART'])
        binary=find_ollama()
    if binary is None:raise ValueError('Ollama installation did not produce its CLI.')
    os.environ['PATH']=str(binary.parent)+os.pathsep+os.environ.get('PATH','')
    if not ollama_ready():
        kwargs={'creationflags':subprocess.DETACHED_PROCESS|subprocess.CREATE_NEW_PROCESS_GROUP|subprocess.CREATE_NO_WINDOW} if SYSTEM=='Windows' else {'start_new_session':True}
        with (ROOT/'data/ollama-startup.log').open('ab') as log:
            subprocess.Popen([str(binary),'serve'],stdout=log,stderr=log,env={**os.environ,'OLLAMA_HOST':'127.0.0.1:11434'},**kwargs)
        for _ in range(60):
            if ollama_ready():break
            time.sleep(1)
        else:raise ValueError('Ollama did not start. See data/ollama-startup.log and rerun setup.')
    return binary


def env_values(path):
    return {k.strip():v.strip().strip('\"\'') for line in path.read_text(encoding='utf-8').splitlines() if '=' in line and not line.lstrip().startswith('#') for k,v in [line.split('=',1)]}


def validate_public_url(value):
    if not value:return ''
    url=urllib.parse.urlsplit(value)
    if url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment or '\n' in value or '\r' in value:raise ValueError('Public URL must use HTTPS without credentials, query or fragment.')
    return value.rstrip('/')


BOOTSTRAP='''from config import Settings
from store import Store
from security import Keys,secret_file
import time
s=Settings.from_env();d=Store(s.data/'alba.sqlite3');uid=s.admins[0]
d.register(uid,'Administrator');d.authorize(uid,s.max_users)
d.set_setting('automatic_web_access','1');d.set_setting('privacy_owner','Alba owner');d.set_setting('privacy_contact','Configure the contact in Settings')
if uid<0:d.execute('INSERT OR IGNORE INTO auth_accounts VALUES(?,?,?,?,?)',('local','owner',uid,'',time.time()))
if not d.rows('SELECT user_id FROM web_credentials WHERE user_id=?',(uid,)):
 k=Keys(d,secret_file(s.data/'auth.key'));name,password=k.set_web_password(uid,uid,'admin')
 p=s.data/'first-access.txt';p.write_text('Username: '+name+'\\nPassword: '+password+'\\n');p.chmod(0o600)
d.close()
'''


def configure(python,model,unattended=False):
    path=ROOT/'.env'
    if path.exists():
        pending=ROOT/'data/setup-initializing'
        if pending.exists():
            run([python,'-c',BOOTSTRAP],cwd=ROOT);pending.unlink()
        print('Existing configuration and credentials preserved.')
        return env_values(path).get('MODEL',model)
    token='' if unattended else getpass.getpass('BotFather token (blank = web only): ').strip()
    admin='' if unattended else input('Telegram administrator ID (blank = local administrator): ').strip()
    if admin and (not admin.isdigit() or int(admin)<1):raise ValueError('Invalid administrator ID.')
    if any(c in token for c in '\r\n'):raise ValueError('Invalid token.')
    url='' if unattended else validate_public_url(input('Public HTTPS URL (optional): ').strip())
    values={'TELEGRAM_BOT_TOKEN':token,'ADMIN_IDS':admin or '-1000000000','MODEL':model,'LLM_BACKEND':'ollama','LLM_URL':'http://127.0.0.1:11434','PUBLIC_URL':url,'CORE_MODEL':'qwen2.5:1.5b','CORE_CODE_MODEL':'qwen2.5-coder:3b','CORE_ADVANCED_CODE_MODEL':'qwen2.5-coder:3b','MAX_USERS':'20','MAX_ONLINE':'5'}
    pending=ROOT/'data/setup-initializing';pending.touch(mode=0o600)
    path.write_text(''.join(k+'='+v+'\n' for k,v in values.items()),encoding='utf-8');path.chmod(0o600)
    run([python,'-c',BOOTSTRAP],cwd=ROOT)
    pending.unlink()
    print('Initial credentials: data/first-access.txt (private).')
    return model


def launch_files(python):
    if SYSTEM=='Windows':
        start=ROOT/'Start Alba.cmd'
        if '%' in str(ROOT):raise ValueError('Windows installation paths cannot contain %.')
        start.write_text('@echo off\ncd /d "'+str(ROOT)+'"\nstart "" "'+str(python.with_name('pythonw.exe'))+'" "'+str(ROOT/'app.py')+'"\n')
    else:
        start=ROOT/'start-alba.sh';start.write_text('#!/bin/sh\ncd '+shlex.quote(str(ROOT))+'\nexport PATH='+shlex.quote(os.environ['PATH'])+'\nexec '+shlex.quote(str(python))+' app.py\n');start.chmod(0o700)
    return start


def start_service(python,launcher):
    if SYSTEM=='Linux':
        if any(c in str(ROOT) for c in '\n\r"%') or ' ' in str(ROOT):raise ValueError('Linux service installation needs a path without spaces, quotes or %. Use --no-service for other paths.')
        unit=(ROOT/'deploy/alba.service').read_text().replace('/home/dvlce/supporto-ai',str(ROOT)).replace('User=alba','User='+getpass.getuser()).replace('Group=alba','Group='+subprocess.check_output(['id','-gn'],text=True).strip())
        unit=unit.replace('ProtectHome=tmpfs\nBindReadOnlyPaths='+str(ROOT),'ProtectHome=read-only')
        unit=unit.replace('Environment=PYTHONUNBUFFERED=1','Environment=PYTHONUNBUFFERED=1\nEnvironment="PATH='+os.environ['PATH'].replace('%','%%')+'"')
        temp=ROOT/'data/alba-install.service';temp.write_text(unit);prefix=[] if os.geteuid()==0 else ['sudo']
        try:run(prefix+['install','-m','644',temp,'/etc/systemd/system/alba.service'])
        finally:temp.unlink(missing_ok=True)
        run(prefix+['systemctl','daemon-reload']);run(prefix+['systemctl','enable','alba']);run(prefix+['systemctl','restart','alba'])
    elif SYSTEM=='Darwin':
        agents=Path.home()/'Library/LaunchAgents';agents.mkdir(parents=True,exist_ok=True);unit=agents/'local.alba.portal.plist'
        unit.write_bytes(plistlib.dumps({'Label':'local.alba.portal','ProgramArguments':[str(python),str(ROOT/'app.py')],'WorkingDirectory':str(ROOT),'EnvironmentVariables':{'PATH':os.environ['PATH'],'PYTHONUNBUFFERED':'1'},'RunAtLoad':True,'KeepAlive':True,'StandardOutPath':str(ROOT/'data/service.log'),'StandardErrorPath':str(ROOT/'data/service.log')}));unit.chmod(0o600)
        domain='gui/'+str(os.getuid());subprocess.run(['launchctl','bootout',domain,str(unit)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);run(['launchctl','bootstrap',domain,unit])
    else:
        startup=Path(os.environ['APPDATA'])/'Microsoft/Windows/Start Menu/Programs/Startup';startup.mkdir(parents=True,exist_ok=True);shutil.copy2(launcher,startup/'Start Alba.cmd')
        with (ROOT/'data/service.log').open('ab') as log:
            subprocess.Popen([str(python.with_name('pythonw.exe')),str(ROOT/'app.py')],cwd=ROOT,stdout=log,stderr=log,creationflags=subprocess.DETACHED_PROCESS|subprocess.CREATE_NEW_PROCESS_GROUP|subprocess.CREATE_NO_WINDOW)
    for _ in range(30):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8088/health',timeout=2) as response:
                if response.status==200:return
        except OSError:pass
        time.sleep(1)
    raise ValueError('Portal did not start. Inspect its service log before rerunning setup.')


def main(argv=None):
    parser=argparse.ArgumentParser(description='Install Alba, Tramonto and Notte on Linux, macOS or Windows.')
    for flag,help_text in [('skip-system','OS dependencies and Ollama already installed'),('no-model','Skip Ollama/model downloads'),('no-service','Create manual launcher, skip autostart'),('with-training','Prepare isolated LoRA training (Linux only)'),('unattended','Web-only local administrator, no prompts'),('plan','Show plan without modifying the machine')]:parser.add_argument('--'+flag,action='store_true',help=help_text)
    args=parser.parse_args(argv)
    if SYSTEM not in ('Linux','Darwin','Windows'):parser.error('Supported systems: Linux, macOS, Windows.')
    if sys.version_info<(3,10):parser.error('Python 3.10 or later is required.')
    if args.with_training:
        from core.prepare_training import supported
        if not supported(SYSTEM):parser.error('Isolated training requires Linux ARM64/Python 3.13 or x86_64/Python 3.10–3.13; lessons and sources work on all three systems.')
    ram=ram_bytes();model='qwen3:4b-instruct-2507-q4_K_M' if ram>=6*2**30 else 'qwen3:1.7b'
    print(json.dumps({'system':SYSTEM,'architecture':platform.machine(),'root':str(ROOT),'ram_gib':round(ram/2**30,1),'initial_model':model,'training':args.with_training,'portal':'http://127.0.0.1:8088'},indent=2))
    if args.plan:return
    os.umask(0o077)
    if SYSTEM=='Windows':
        owner=subprocess.check_output(['whoami'],text=True).strip()
        run(['icacls',ROOT,'/inheritance:r','/grant:r',owner+':(OI)(CI)F','SYSTEM:(OI)(CI)F'])
    for name in ('data','backups'):(ROOT/name).mkdir(mode=0o700,exist_ok=True)
    if not args.skip_system:system_packages(args.with_training)
    python=python_path(ROOT)
    if not python.exists():venv.create(ROOT/'.venv',with_pip=True)
    run([python,'-m','pip','install','-r',ROOT/'requirements.txt'])
    model=configure(python,model,args.unattended)
    if not args.no_model:
        ollama=install_ollama(args.skip_system);config=env_values(ROOT/'.env')
        for name in dict.fromkeys([model,config.get('CORE_MODEL','qwen2.5:1.5b'),config.get('CORE_CODE_MODEL','qwen2.5-coder:3b'),'embeddinggemma']):run([ollama,'pull',name])
    if args.with_training:run([python,ROOT/'core/prepare_training.py',ROOT/'data/core-training'],cwd=ROOT)
    launcher=launch_files(python)
    if not args.no_service:start_service(python,launcher)
    print('Setup complete. Open http://127.0.0.1:8088; initial credentials: data/first-access.txt.')
    print('For remote access configure PUBLIC_URL and an HTTPS reverse proxy. Manual launcher: '+str(launcher))
    if SYSTEM!='Linux':print('Isolated Python exercises, SPICE and LoRA training require Linux. Lessons, sources, chat and notebooks are available here.')


if __name__=='__main__':main()
