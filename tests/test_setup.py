"""Installer boundaries, resume preservation and platform command generation."""
import hashlib
import gzip
import io
import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from deploy.setup_bundle import allowed,unpack
from deploy import portable_install as installer


def archive(files,extra=()):
    manifest={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
    output=io.BytesIO()
    with tarfile.open(fileobj=output,mode='w:gz') as tar:
        for name,data in list(files.items())+[('setup-manifest.json',json.dumps(manifest).encode())]:
            info=tarfile.TarInfo(name);info.size=len(data);tar.addfile(info,io.BytesIO(data))
        for info in extra:tar.addfile(info)
    return output.getvalue()


class SetupTests(unittest.TestCase):
    def test_private_and_foreign_paths_rejected(self):
        for name in ('.env','data/auth.key','backups/private.sai','../app.py','/tmp/app.py','C:/app.py','vendor/../../app.py','core\\app.py','deploy/harden_pi.py','whatsapp/.env','vendor/.secret'):
            with self.subTest(name=name):self.assertFalse(allowed(name))
        for name in ('app.py','install.py','LICENSE','vendor/fonts/book-latin.woff2','deploy/portable_install.py','core/knowledge.py'):self.assertTrue(allowed(name))

    def test_resume_preserves_credentials_and_data(self):
        raw=archive({'app.py':b'print("app")','vendor/license.txt':b'license'})
        with tempfile.TemporaryDirectory() as folder:
            root=unpack(raw,Path(folder)/'new machine');(root/'data').mkdir();(root/'.env').write_text('SECRET=example');(root/'data/lesson.txt').write_text('private')
            unpack(raw,root)
            self.assertEqual((root/'.env').read_text(),'SECRET=example');self.assertEqual((root/'data/lesson.txt').read_text(),'private')
            self.assertFalse((root/'app.py.setup-tmp').exists())

    def test_existing_installation_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'.env').write_text('KEEP')
            with self.assertRaises(ValueError):unpack(archive({'app.py':b'new'}),root)
            self.assertEqual((root/'.env').read_text(),'KEEP');self.assertFalse((root/'app.py').exists())

    def test_tar_traversal_symlinks_and_duplicates(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'new'
            for name in ('../escape.py','data/private.py','/tmp/escape.py'):
                with self.assertRaises(ValueError):unpack(archive({name:b'bad'}),target)
            link=tarfile.TarInfo('app.py');link.type=tarfile.SYMTYPE;link.linkname='../other'
            with self.assertRaises(ValueError):unpack(archive({},[link]),target)
            duplicate=tarfile.TarInfo('app.py')
            with self.assertRaises(ValueError):unpack(archive({'app.py':b'x'},[duplicate]),target)
            self.assertFalse(target.exists())

    def test_corruption_and_changed_code_fail_before_writing(self):
        raw=archive({'app.py':b'old','config.py':b'config'})
        with tempfile.TemporaryDirectory() as folder:
            root=unpack(raw,Path(folder)/'new');(root/'app.py').write_bytes(b'edited')
            with self.assertRaises(ValueError):unpack(raw,root)
            self.assertEqual((root/'app.py').read_bytes(),b'edited')
            broken=gzip.compress(gzip.decompress(raw).replace(b'old',b'new',1))
            with self.assertRaisesRegex(ValueError,'hash mismatch'):unpack(broken,Path(folder)/'broken')

    def test_destination_symlink_escape_rejected(self):
        if os.name=='nt':self.skipTest('Windows symlinks need privileges')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'new';root.mkdir();(root/'vendor').symlink_to(Path(folder)/'other',target_is_directory=True)
            with self.assertRaises(ValueError):unpack(archive({'vendor/file.js':b'bad'}),root)
            self.assertFalse((Path(folder)/'other').exists())

    def test_https_origin_validation(self):
        self.assertEqual(installer.validate_public_url('https://alba.example/'),'https://alba.example')
        for value in ('http://example','https://user:pass@example','https://example?token=x','https://example\nTOKEN=bad'):
            with self.assertRaises(ValueError):installer.validate_public_url(value)

    def test_existing_configuration_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(installer,'ROOT',Path(folder)),patch.object(installer,'run') as run:
            (Path(folder)/'.env').write_text('MODEL=custom\nTELEGRAM_BOT_TOKEN=private\n')
            self.assertEqual(installer.configure(Path('/python'),'default',True),'custom')
            run.assert_not_called();self.assertIn('private',(Path(folder)/'.env').read_text())

    def test_interrupted_bootstrap_resumes_without_password_reset(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(installer,'ROOT',Path(folder)),patch.object(installer,'run') as run:
            root=Path(folder);(root/'data').mkdir();(root/'.env').write_text('MODEL=custom');(root/'data/setup-initializing').touch()
            installer.configure(Path('/python'),'default',True)
            run.assert_called_once();self.assertFalse((root/'data/setup-initializing').exists())
            self.assertIn('SELECT user_id FROM web_credentials',installer.BOOTSTRAP)

    def test_windows_and_unix_launcher_paths(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(installer,'ROOT',Path(folder)):
            with patch.object(installer,'SYSTEM','Windows'):
                path=installer.launch_files(Path(folder)/'.venv/Scripts/python.exe');self.assertIn('pythonw.exe',path.read_text());self.assertIn('cd /d "',path.read_text())
            with patch.object(installer,'SYSTEM','Darwin'):
                path=installer.launch_files(Path(folder)/'.venv/bin/python');self.assertIn('exec ',path.read_text())
                if os.name!='nt':self.assertEqual(path.stat().st_mode&0o777,0o700)

    def test_non_linux_training_stops_before_mutation(self):
        with patch.object(installer,'SYSTEM','Windows'),patch.object(installer,'system_packages') as packages:
            with self.assertRaises(SystemExit):installer.main(['--with-training'])
            packages.assert_not_called()

    def test_training_supported_host_matrix(self):
        from core.prepare_training import supported
        self.assertTrue(supported('Linux','aarch64',(3,13)))
        self.assertTrue(supported('Linux','x86_64',(3,12)))
        for host in [('Linux','aarch64',(3,12)),('Darwin','arm64',(3,13)),('Windows','AMD64',(3,13)),('Linux','x86_64',(3,14))]:
            with self.subTest(host=host):self.assertFalse(supported(*host))


if __name__=='__main__':unittest.main()
