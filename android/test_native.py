"""Build a separate, same-certificate instrumentation APK; never part of release."""
import argparse,os,subprocess,zipfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--sdk',default=str(Path.home()/'.local/alba-android-sdk'));args=p.parse_args()
root=Path(__file__).resolve().parent;work=root/'build/smoke';work.mkdir(parents=True,exist_ok=True);sdk=Path(args.sdk);tools=sdk/'build-tools/36.0.0';jar=sdk/'platforms/android-36/android.jar';classes=work/'classes';classes.mkdir(exist_ok=True);dex=work/'dex';dex.mkdir(exist_ok=True)
manifest=work/'AndroidManifest.xml';manifest.write_text('<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="local.alba.smoke"><uses-sdk android:minSdkVersion="23" android:targetSdkVersion="36"/><application android:label="Alba native test"/><instrumentation android:name="local.alba.NativeUiSmoke" android:targetPackage="local.alba" android:functionalTest="true"/></manifest>')
def run(values):subprocess.run([str(v) for v in values],check=True)
run(['javac','--release','8','-classpath',str(jar)+os.pathsep+str(root/'build/classes'),'-d',classes,*sorted((root/'tests').rglob('*.java'))])
run([tools/'d8','--min-api','23','--lib',jar,'--classpath',root/'build/classes','--output',dex,*sorted(classes.rglob('*.class'))])
run([tools/'aapt','package','-f','-M',manifest,'-A',root/'tests/assets','-I',jar,'-F',work/'unsigned.apk'])
with zipfile.ZipFile(work/'unsigned.apk','a') as out:out.write(dex/'classes.dex','classes.dex')
run([tools/'zipalign','-f','4',work/'unsigned.apk',work/'aligned.apk'])
sign=Path.home()/'.local/alba-signing';os.environ['ALBA_SIGN_PASS']=(sign/'password').read_text()
run([tools/'apksigner','sign','--ks',sign/'alba-release.p12','--ks-key-alias','alba','--ks-pass','env:ALBA_SIGN_PASS','--out',work/'native-smoke.apk',work/'aligned.apk'])
print('Instrumentation:',work/'native-smoke.apk')
