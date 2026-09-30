"""Streaming authenticated encryption, online SQLite snapshots and offline restore."""
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from security import secret_file

MAGIC = b'SAI1'


class Backups:
    def __init__(self, store, settings):
        self.store,self.settings = store,settings
        self.root = settings.root/'backups'
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        os.chmod(self.root,0o700)
        self.key = secret_file(settings.data/'backup.key')

    def encrypt(self, source, destination):
        iv = os.urandom(12)
        encryptor = Cipher(algorithms.AES(self.key),modes.GCM(iv)).encryptor()
        encryptor.authenticate_additional_data(MAGIC)
        with open(source,'rb') as src, open(destination,'wb') as dst:
            os.chmod(destination,0o600)
            dst.write(MAGIC+iv)
            while block := src.read(1024*1024):
                dst.write(encryptor.update(block))
            dst.write(encryptor.finalize())
            dst.write(encryptor.tag)

    def decrypt(self, source, destination):
        with open(source,'rb') as src:
            size = os.fstat(src.fileno()).st_size
            if size<32 or src.read(4)!=MAGIC:
                raise ValueError('Backup non valido.')
            iv = src.read(12)
            src.seek(-16,2)
            tag = src.read(16)
            decryptor = Cipher(algorithms.AES(self.key),modes.GCM(iv,tag)).decryptor()
            decryptor.authenticate_additional_data(MAGIC)
            src.seek(16)
            remaining = size-32
            with open(destination,'wb') as dst:
                os.chmod(destination,0o600)
                while remaining:
                    block = src.read(min(1024*1024,remaining))
                    remaining -= len(block)
                    dst.write(decryptor.update(block))
                dst.write(decryptor.finalize())

    def create(self, kind='daily', now=None):
        if kind not in ('daily','weekly','monthly','manual'):
            raise ValueError('Tipo backup non valido.')
        now = now or datetime.now(timezone.utc)
        target = self.root/f'{kind}_{now.strftime("%Y%m%dT%H%M%S%f")}.sai'
        with tempfile.TemporaryDirectory(dir=self.settings.data) as tmp:
            snapshot = Path(tmp)/'snapshot.sqlite3'
            db = sqlite3.connect(snapshot)
            self.store.db.backup(db,pages=256)
            db.close()
            self.encrypt(snapshot,target)
        retention = {'daily':self.settings.daily_retention,'weekly':self.settings.weekly_retention,
                     'monthly':self.settings.monthly_retention,'manual':3}[kind]
        for old in sorted(self.root.glob(kind+'_*.sai'),reverse=True)[max(1,retention):]:
            old.unlink()
        return target

    def scheduled(self, now=None):
        now = now or datetime.now(timezone.utc)
        for kind, marker in [('daily',now.strftime('%Y-%m-%d')),
                             ('weekly',now.strftime('%G-%V')),('monthly',now.strftime('%Y-%m'))]:
            if self.store.setting('backup_'+kind)!=marker:
                self.create(kind,now)
                self.store.set_setting('backup_'+kind,marker)

    def purge_after_erasure(self):
        # Erasure must also remove earlier snapshots; a restore must not resurrect private data.
        for path in self.root.glob('*.sai'):
            path.unlink()
        self.create('daily')

    def restore(self, source, destination):
        destination = Path(destination)
        if destination.resolve()==self.store.path.resolve():
            raise ValueError('Ferma il servizio e usa maintenance.py per il ripristino offline.')
        destination.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=destination.parent) as tmp:
            restored = Path(tmp)/'restore.sqlite3'
            self.decrypt(source,restored)
            db = sqlite3.connect(restored)
            try:
                if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                    raise ValueError('Database backup danneggiato.')
                db.execute('UPDATE export_keys SET revoked=1')
                db.execute('DELETE FROM web_sessions')
                if db.execute("SELECT name FROM sqlite_master WHERE name='auth_flows'").fetchone(): db.execute('DELETE FROM auth_flows')
                if db.execute("SELECT name FROM sqlite_master WHERE name='memory_access_grants'").fetchone(): db.execute('DELETE FROM memory_access_grants')
                if db.execute("SELECT name FROM sqlite_master WHERE name='web_credentials'").fetchone():
                    db.execute('DELETE FROM web_credentials')
                db.execute("UPDATE app_settings SET value='' WHERE key='bootstrap_digest'")
                db.commit()
            finally:
                db.close()
            os.replace(restored,destination)
            os.chmod(destination,0o600)
