"""Install one-file payload in a fresh directory and verify native portal startup.
No autostart changes, OS package changes, models or private production data.
"""
import hashlib
import argparse
import http.cookiejar
import json
import os
import platform
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.parse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--installers',type=Path);options=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='alba-setup-test-') as directory:
        work=Path(directory);output=options.installers or work/'downloads';target=work/'new machine'
        if options.installers is None:subprocess.run([sys.executable,str(ROOT/'tools/build_setup.py'),'--output',str(output)],check=True)
        system=platform.system()
        if system=='Windows':command=['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(output/'alba-setup-windows.ps1')]
        else:command=['sh',str(output/('alba-setup-macos.command' if system=='Darwin' else 'alba-setup-linux.sh'))]
        flags=['--directory',str(target),'--unattended','--skip-system','--no-model','--no-service']
        subprocess.run(command+flags,check=True,timeout=420)
        python=target/('.venv/Scripts/python.exe' if system=='Windows' else '.venv/bin/python')
        credentials=(target/'data/first-access.txt').read_bytes();key=(target/'data/auth.key').read_bytes()
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        with (target/'.env').open('a') as file:file.write('WEB_PORT='+str(port)+'\n')
        base='http://127.0.0.1:'+str(port)
        class LoopbackCookiePolicy(http.cookiejar.DefaultCookiePolicy):
            def return_ok_secure(self,cookie,request):
                # Match browsers' Secure-cookie exception for this loopback test.
                return urllib.parse.urlsplit(request.full_url).hostname=='127.0.0.1' or super().return_ok_secure(cookie,request)
        opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar(policy=LoopbackCookiePolicy())))
        def api(path,body=None,csrf=''):
            req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','X-CSRF-Token':csrf})
            with opener.open(req,timeout=20) as response:return json.load(response)
        with (work/'startup.log').open('wb') as log:
            process=subprocess.Popen([str(python),str(target/'app.py')],cwd=target,stdout=log,stderr=log)
            try:
                for _ in range(60):
                    if process.poll() is not None:raise AssertionError('Portal exited: '+(work/'startup.log').read_text())
                    try:
                        if api('/health')['status']=='ok':break
                    except OSError:time.sleep(.5)
                else:raise AssertionError('Portal startup timeout')
                values=dict(line.split(': ',1) for line in credentials.decode().splitlines())
                api('/api/login',{'username':values['Username'],'password':values['Password']})
                me=api('/api/me');assert me['is_admin']
                state=api('/api/notte/status');assert state['config']['advanced_code_model']==state['config']['code_model']
                with opener.open(base+'/notte') as response:assert 'id="panel-system"' in response.read().decode()
                api('/api/notte/knowledge',{'title':'Fresh setup lesson','text':'The setup verification identifier is CLEAR-SKY-42.'},me['csrf'])
                knowledge=api('/api/notte/knowledge');assert knowledge['documents']==1 and knowledge['indexed_percent']==100
            finally:
                process.terminate()
                try:process.wait(timeout=15)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        subprocess.run(command+flags,check=True,timeout=180)
        assert (target/'data/first-access.txt').read_bytes()==credentials
        assert (target/'data/auth.key').read_bytes()==key
        print('Native one-file setup OK: '+system+'; portal, administrator login, persistent lesson and safe resume. No models downloaded.')


if __name__=='__main__':main()
