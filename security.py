import asyncio
import hashlib
import hmac
import os
import re
import secrets
import time
from pathlib import Path
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


def secret_file(path):
    path = Path(path)
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    if not path.exists():
        try:
            fd = os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd,'wb') as f:
                f.write(secrets.token_bytes(32))
    os.chmod(path,0o600)
    value = path.read_bytes()
    if len(value)!=32:
        raise ValueError('Chiave locale non valida.')
    return value


class Keys:
    SESSION_TTL=43200
    REMEMBER_TTL=90*86400
    def __init__(self, store, pepper):
        self.store, self.pepper = store, pepper
        self.is_admin = lambda actor: False

    def digest(self, token):
        return hmac.new(self.pepper,token.encode(),hashlib.sha256).hexdigest()

    def issue(self, actor, target, purpose='export', ttl=900):
        if purpose not in ('export','delegate','test','web','memory_read'):
            raise ValueError('Scopo della chiave non valido.')
        if actor!=target and purpose!='test':
            raise PermissionError('Solo il proprietario può autorizzare dati reali.')
        if purpose=='test' and not self.is_admin(actor):
            raise PermissionError('Solo l’amministratore può creare chiavi di test.')
        if not self.store.allowed(target):
            raise PermissionError('Utente non autorizzato.')
        token = secrets.token_urlsafe(32)
        self.store.execute('INSERT INTO export_keys(user_id,digest,purpose,expires,created) VALUES(?,?,?,?,?)',
                            (target,self.digest(token),purpose,time.time()+ttl,time.time()))
        self.store.audit(actor,'key_issue_'+purpose,target)
        return token

    def consume(self, actor, target, token, purposes=('export',)):
        with self.store.db:
            row = self.store.db.execute('SELECT * FROM export_keys WHERE digest=?',(self.digest(token),)).fetchone()
            valid = (row and row['user_id']==target and row['purpose'] in purposes and
                     row['expires']>time.time() and not row['used'] and not row['revoked'])
            if valid and row['purpose'] in ('export','web') and actor!=target:
                valid = False
            if valid and row['purpose'] in ('delegate','test','memory_read') and not self.is_admin(actor):
                valid = False
            if not valid:
                self.store.audit(actor,'key_use',target,'denied')
                raise PermissionError('Chiave non valida, scaduta, revocata o già utilizzata.')
            changed = self.store.db.execute('UPDATE export_keys SET used=1 WHERE id=? AND used=0',(row['id'],))
            if changed.rowcount!=1:
                raise PermissionError('Chiave già utilizzata.')
        self.store.audit(actor,'key_use_'+row['purpose'],target)
        return row['purpose']

    def revoke(self, actor, target):
        self.store.execute('UPDATE export_keys SET revoked=1 WHERE user_id=?',(target,))
        self.store.execute('DELETE FROM web_sessions WHERE user_id=?',(target,))
        self.store.execute('DELETE FROM memory_access_grants WHERE user_id=? OR admin_id=?',(target,target))
        self.store.audit(actor,'key_revoke',target)

    def session(self, token,remember=False,label='Browser'):
        # Owner id is resolved from the key, never taken from an HTTP client.
        row = self.store.rows('SELECT user_id FROM export_keys WHERE digest=?',(self.digest(token),))
        if not row:
            raise PermissionError('Accesso non valido.')
        uid = row[0]['user_id']
        self.consume(uid,uid,token,('web',))
        return self.create_session(uid,remember,label)

    def create_session(self,uid,remember=False,label='Browser'):
        if not self.store.allowed(uid):
            raise PermissionError('Utente non autorizzato.')
        session, csrf = secrets.token_urlsafe(32),secrets.token_urlsafe(24)
        now=time.time(); ttl=self.REMEMBER_TTL if remember else self.SESSION_TTL
        self.store.execute('DELETE FROM web_sessions WHERE expires<=?',(now,))
        self.store.execute('INSERT INTO web_sessions(digest,user_id,csrf,expires,device_id,label,remembered,created,last_seen) VALUES(?,?,?,?,?,?,?,?,?)',
                            (self.digest(session),uid,csrf,now+ttl,secrets.token_urlsafe(12),label[:80],int(remember),now,now))
        return session,csrf

    @staticmethod
    def password_hash(password,salt):
        return Scrypt(salt=salt,length=32,n=16384,r=8,p=1).derive(password.encode())

    def set_web_password(self,actor,target,username=None):
        if actor!=target and not self.is_admin(actor):
            raise PermissionError('Operazione non autorizzata.')
        if not self.store.allowed(target):
            raise PermissionError('Utente non autorizzato.')
        existing=self.store.rows('SELECT username FROM web_credentials WHERE user_id=?',(target,))
        username=username or (existing[0]['username'] if existing else 'user_'+str(target))
        if not re.fullmatch(r'[a-z0-9_.-]{3,32}',username):
            raise ValueError('Nome di accesso non valido.')
        conflict=self.store.rows('SELECT user_id FROM web_credentials WHERE username=?',(username,))
        if conflict and conflict[0]['user_id']!=target:
            raise ValueError('Nome di accesso già assegnato.')
        password=secrets.token_urlsafe(18); salt=secrets.token_bytes(16)
        digest=self.password_hash(password,salt)
        with self.store.db:
            self.store.db.execute('INSERT INTO web_credentials VALUES(?,?,?,?,?) '
                'ON CONFLICT(user_id) DO UPDATE SET username=excluded.username,salt=excluded.salt,'
                'password_hash=excluded.password_hash,created=excluded.created',
                (target,username,salt,digest,time.time()))
            self.store.db.execute('DELETE FROM web_sessions WHERE user_id=?',(target,))
        self.store.audit(actor,'web_password_reset',target)
        return username,password

    async def password_session(self,username,password,remember=False,label='Browser'):
        if not isinstance(username,str) or not isinstance(password,str) or len(username)>64 or len(password)>256:
            raise PermissionError('Nome utente o password non validi.')
        rows=self.store.rows('SELECT * FROM web_credentials WHERE username=?',(username.strip().casefold(),))
        row=rows[0] if rows else None
        # Unknown names use the same password hashing cost, without revealing registered accounts.
        salt=row['salt'] if row else b'\x00'*16
        calculated=await asyncio.to_thread(self.password_hash,password,salt)
        expected=row['password_hash'] if row else b'\x00'*32
        current=self.store.rows('SELECT password_hash FROM web_credentials WHERE user_id=?',(row['user_id'],)) if row else []
        if (not secrets.compare_digest(calculated,expected) or not current or
                not secrets.compare_digest(current[0]['password_hash'],expected) or
                not self.store.allowed(row['user_id'])):
            raise PermissionError('Nome utente o password non validi.')
        self.store.audit(row['user_id'],'password_login',row['user_id'])
        return self.create_session(row['user_id'],remember,label)

    def renew_session(self,digest):
        rows=self.store.rows('SELECT * FROM web_sessions WHERE digest=? AND expires>?',(digest,time.time()))
        if not rows or not self.store.allowed(rows[0]['user_id']): return False
        row=rows[0]; now=time.time()
        renew=bool(row['remembered'] and row['expires']-now<self.REMEMBER_TTL-86400)
        if renew or now-row['last_seen']>=300:
            self.store.execute('UPDATE web_sessions SET last_seen=?,expires=? WHERE digest=?',
                               (now,now+self.REMEMBER_TTL if renew else row['expires'],digest))
        return renew

    def revoke_web_password(self,actor,target):
        if actor!=target and not self.is_admin(actor):
            raise PermissionError('Operazione non autorizzata.')
        self.store.execute('DELETE FROM web_credentials WHERE user_id=?',(target,))
        self.store.execute('DELETE FROM web_sessions WHERE user_id=?',(target,))
        self.store.execute('DELETE FROM memory_access_grants WHERE user_id=? OR admin_id=?',(target,target))
        self.store.audit(actor,'web_password_revoke',target)

    def identify(self, session):
        row = self.store.rows('SELECT * FROM web_sessions WHERE digest=? AND expires>?',
                              (self.digest(session),time.time()))
        if not row or not self.store.allowed(row[0]['user_id']):
            raise PermissionError('Accedi con una nuova /web_key da Telegram.')
        return row[0]
