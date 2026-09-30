#!/usr/bin/env python3
"""Interactive Linux installer. Keeps secrets out of shell arguments and creates an isolated venv."""
import argparse,getpass,json,os,platform,shutil,subprocess,sys,urllib.request,venv
from pathlib import Path
parser=argparse.ArgumentParser(description='Installa Alba sul tuo Linux/Raspberry. Il download di Ollama richiede internet solo durante setup/modelli.');parser.add_argument('--skip-system',action='store_true',help='Pacchetti e Ollama già installati');parser.add_argument('--no-model',action='store_true');parser.add_argument('--no-service',action='store_true');args=parser.parse_args();root=Path(__file__).resolve().parent;os.umask(0o077)
if platform.system()!='Linux':parser.error('Installer automatico per Linux. Su altri sistemi: python3 -m venv .venv, pip install -r requirements.txt e Ollama; SPICE isolato richiede Linux.')
ram=int(next((line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemTotal:')),'0'))*1024;disk=shutil.disk_usage(root);print('Hardware:',platform.machine(),os.cpu_count(),'CPU,',round(ram/2**30,1),'GiB RAM,',round(disk.free/2**30,1),'GiB liberi')
model='qwen3:4b-instruct-2507-q4_K_M' if ram>=6*2**30 else 'qwen3:1.7b';print('Modello iniziale:',model,'· backend sostituibile in .env')
if not args.skip_system:
 subprocess.run(['sudo','apt-get','update'],check=True);subprocess.run(['sudo','apt-get','install','-y','python3-venv','python3-pip','curl','ngspice','bubblewrap'],check=True)
 if not shutil.which('ollama'):
  path=root/'data/ollama-install.sh';path.parent.mkdir(mode=0o700,exist_ok=True);urllib.request.urlretrieve('https://ollama.com/install.sh',path);subprocess.run(['sh',str(path)],check=True);path.unlink()
venv.create(root/'.venv',with_pip=True);python=root/'.venv/bin/python';subprocess.run([str(python),'-m','pip','install','-r',str(root/'requirements.txt')],check=True)
env=root/'.env'
if not env.exists():
 token=getpass.getpass('Token BotFather (vuoto = solo web; non sarà mostrato): ').strip();admin=input('ID Telegram amministratore (vuoto = admin locale da terminale): ').strip()
 if admin and (not admin.isdigit() or int(admin)<1):parser.error('ID Telegram non valido.')
 uid=int(admin) if admin else -1000000000;url=input('URL pubblico HTTPS (facoltativo, es. https://alba.example.org): ').strip().rstrip('/')
 if url and not url.startswith('https://'):parser.error('Usa HTTPS per il sito pubblico.')
 env.write_text('TELEGRAM_BOT_TOKEN='+token+'\nADMIN_IDS='+str(uid)+'\nMODEL='+model+'\nLLM_BACKEND=ollama\nLLM_URL=http://127.0.0.1:11434\nPUBLIC_URL='+url+'\nMAX_USERS=20\nMAX_ONLINE=5\n');env.chmod(0o600)
 subprocess.run([str(python),'-c',"from config import Settings;from store import Store;from security import Keys,secret_file;import time; s=Settings.from_env();d=Store(s.data/'alba.sqlite3');uid=s.admins[0];d.register(uid,'Amministratore');d.authorize(uid,s.max_users);d.set_setting('automatic_web_access','1');d.set_setting('privacy_owner','Gestore Alba');d.set_setting('privacy_contact','Configura il contatto nel pannello');\nif uid<0:d.execute('INSERT OR IGNORE INTO auth_accounts VALUES(?,?,?,?,?)',('local','owner',uid,'',time.time()))\nk=Keys(d,secret_file(s.data/'auth.key'));name,password=k.set_web_password(uid,uid,'admin');p=s.root/'data/first-access.txt';p.write_text('Username: '+name+'\\nPassword: '+password+'\\n');p.chmod(0o600);d.close()"],check=True,cwd=root)
 print('Credenziali iniziali protette in data/first-access.txt. Leggile dal terminale e rimuovi il file dopo averle conservate.')
else:
 print('.env esistente conservato. Nessuna credenziale reimpostata.')
 for line in env.read_text().splitlines():
  if line.startswith('MODEL='):
   model=line.split('=',1)[1].strip().strip('\"').strip("'") or model
   break
if not args.no_model:subprocess.run(['ollama','pull',model],check=True)
if not args.no_service:
 user=getpass.getuser();unit=(root/'deploy/alba.service').read_text().replace('/home/dvlce/supporto-ai',str(root)).replace('User=alba','User='+user).replace('Group=alba','Group='+str(subprocess.check_output(['id','-gn'],text=True).strip()));unit=unit.replace('ProtectHome=tmpfs\nBindReadOnlyPaths='+str(root),'ProtectHome=read-only')
 temporary=root/'data/alba-install.service';temporary.write_text(unit);subprocess.run(['sudo','install','-m','644',str(temporary),'/etc/systemd/system/alba.service'],check=True);temporary.unlink();subprocess.run(['sudo','systemctl','daemon-reload'],check=True);subprocess.run(['sudo','systemctl','enable','--now','alba'],check=True)
print('Setup completo. Il server ascolta solo su 127.0.0.1:8088. Pubblicalo con un reverse proxy HTTPS e configura PUBLIC_URL. SSH/firewall non vengono modificati dall’installer. Vedi SICUREZZA.md e ACCESSI_ESTERNI.md.')
