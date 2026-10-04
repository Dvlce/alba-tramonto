#!/usr/bin/env python3
"""Build the signed standalone WebView Android client using SDK 36 and JDK 17."""
import argparse,hashlib,os,secrets,shutil,subprocess,zipfile,json,re
from pathlib import Path
from xml.sax.saxutils import escape
from urllib.parse import urlsplit
parser=argparse.ArgumentParser();parser.add_argument('--sdk',default=os.environ.get('ANDROID_SDK_ROOT',str(Path.home()/'.local/alba-android-sdk')));parser.add_argument('--server',default='https://alba.example.org');parser.add_argument('--output',default='dist/alba-albi.apk');parser.add_argument('--signing-dir',default=str(Path.home()/'.local/alba-signing'));args=parser.parse_args()
root=Path(__file__).resolve().parent;sdk=Path(args.sdk);tools=sdk/'build-tools/36.0.0';jar=sdk/'platforms/android-36/android.jar';work=root/'build';work.mkdir(exist_ok=True);(work/'classes').mkdir(exist_ok=True);(work/'dex').mkdir(exist_ok=True)
server=urlsplit(args.server)
if server.scheme!='https' or not server.hostname or server.username or server.password or server.query or server.fragment or server.path not in ('','/'):
 raise SystemExit('Il server deve essere una origine HTTPS valida.')
manifest=work/'AndroidManifest.xml'
manifest.write_text((root/'AndroidManifest.xml').read_text().replace('android:host="alba.example.org"','android:host="'+escape(server.hostname)+'"'))
resources=work/'res';shutil.copytree(root/'res',resources,dirs_exist_ok=True)
(resources/'values/strings.xml').write_text('<resources><string name="default_server">'+escape(args.server)+'</string></resources>')
for stale in (work/'classes').rglob('*.class'): stale.unlink()
def run(values):subprocess.run([str(x) for x in values],check=True,stdout=subprocess.DEVNULL)
(work/'generated').mkdir(exist_ok=True)
run([tools/'aapt','package','-f','-m','-J',work/'generated','-M',manifest,'-S',resources,'-I',jar,'-F',work/'unsigned.apk'])
run(['javac','--release','8','-classpath',jar,'-d',work/'classes',root/'src/local/alba/MainActivity.java',*sorted((work/'generated').rglob('*.java'))])
run([tools/'d8','--min-api','23','--lib',jar,'--output',work/'dex',*sorted((work/'classes').rglob('*.class'))])

with zipfile.ZipFile(work/'unsigned.apk','a',zipfile.ZIP_DEFLATED) as output:output.write(work/'dex/classes.dex','classes.dex')
run([tools/'zipalign','-f','4',work/'unsigned.apk',work/'aligned.apk'])
sign=Path(args.signing_dir);sign.mkdir(mode=0o700,parents=True,exist_ok=True);password=sign/'password';key=sign/'alba-release.p12'
if not password.exists():password.write_text(secrets.token_urlsafe(40));password.chmod(0o600)
os.environ['ALBA_SIGN_PASS']=password.read_text()
if not key.exists():run(['keytool','-genkeypair','-keystore',key,'-alias','alba','-storetype','PKCS12','-keyalg','RSA','-keysize','3072','-validity','10000','-dname','CN=Alba Open Source','-storepass:env','ALBA_SIGN_PASS']);key.chmod(0o600)
output=Path(args.output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
run([tools/'apksigner','sign','--ks',key,'--ks-key-alias','alba','--ks-pass','env:ALBA_SIGN_PASS','--out',output,work/'aligned.apk']);run([tools/'apksigner','verify',output]);print('APK verificato:',output);print('SHA256:',hashlib.sha256(output.read_bytes()).hexdigest())

certificate=subprocess.check_output([str(tools/'apksigner'),'verify','--print-certs',str(output)],text=True)
digest=re.search(r'certificate SHA-256 digest: ([0-9a-fA-F]{64})',certificate).group(1).upper()
fingerprint=':'.join(digest[i:i+2] for i in range(0,64,2))
association=[{'relation':['delegate_permission/common.handle_all_urls'],'target':{'namespace':'android_app','package_name':'local.alba','sha256_cert_fingerprints':[fingerprint]}}]
(output.parent/'assetlinks.json').write_text(json.dumps(association,indent=2)+'\n')
print('App Links host:',server.hostname)
print('App Links certificate:',fingerprint)
