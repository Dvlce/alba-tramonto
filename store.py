"""SQLite, provenance and explicit namespaces. No unscoped retrieval API."""
import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

PERSONALITY = dict(humor=.3, empathy=.85, curiosity=.65, formality=.2,
                   verbosity=.4, directness=.65)
CATEGORIES = {'episodic', 'personal', 'preference', 'goal', 'relationship',
              'event', 'temporary', 'group'}
SCHEMA = '''
CREATE TABLE IF NOT EXISTS memory_access_grants(user_id INTEGER NOT NULL,admin_id INTEGER NOT NULL,expires REAL NOT NULL,created REAL NOT NULL,PRIMARY KEY(user_id,admin_id));
CREATE TABLE IF NOT EXISTS response_feedback(user_id INTEGER NOT NULL,message_id INTEGER NOT NULL,label TEXT NOT NULL,timestamp REAL NOT NULL,PRIMARY KEY(user_id,message_id));
CREATE INDEX IF NOT EXISTS response_feedback_owner ON response_feedback(user_id,timestamp DESC);
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL,
 authorized INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS telegram_chats(id INTEGER PRIMARY KEY, kind TEXT, title TEXT);
CREATE TABLE IF NOT EXISTS groups(id INTEGER PRIMARY KEY, enabled INTEGER DEFAULT 0,
 auto_mode INTEGER DEFAULT 0, last_auto REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS conversations(scope TEXT PRIMARY KEY, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, scope TEXT NOT NULL,
 user_id INTEGER, role TEXT NOT NULL, content TEXT NOT NULL, timestamp REAL NOT NULL,
 telegram_chat_id INTEGER, telegram_message_id INTEGER, reply_id INTEGER,
 mentions TEXT DEFAULT '[]', thread_id INTEGER DEFAULT 0,
 UNIQUE(telegram_chat_id,telegram_message_id));
CREATE INDEX IF NOT EXISTS messages_scope_time ON messages(scope,id DESC);
CREATE INDEX IF NOT EXISTS messages_author ON messages(user_id,role);
CREATE TABLE IF NOT EXISTS memories(id INTEGER PRIMARY KEY, scope TEXT NOT NULL,
 user_id INTEGER, group_id INTEGER, content TEXT NOT NULL, category TEXT NOT NULL,
 timestamp REAL NOT NULL, importance REAL NOT NULL, confidence REAL NOT NULL,
 status TEXT CHECK(status IN ('active','historical','uncertain','deleted')) NOT NULL,
 evidence TEXT CHECK(evidence IN ('fact','inference','uncertain')) NOT NULL,
 source_ids TEXT NOT NULL, expires REAL, exportable INTEGER DEFAULT 1, summary_id INTEGER);
CREATE INDEX IF NOT EXISTS memories_scope_status ON memories(scope,status,category);
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(content,tokenize='unicode61 remove_diacritics 2');
CREATE TRIGGER IF NOT EXISTS memory_insert AFTER INSERT ON memories BEGIN
 INSERT INTO memory_fts(rowid,content) VALUES(new.id,new.content); END;
CREATE TRIGGER IF NOT EXISTS memory_delete AFTER DELETE ON memories BEGIN
 DELETE FROM memory_fts WHERE rowid=old.id; END;
CREATE TRIGGER IF NOT EXISTS memory_update AFTER UPDATE OF content ON memories BEGIN
 DELETE FROM memory_fts WHERE rowid=old.id;
 INSERT INTO memory_fts(rowid,content) VALUES(new.id,new.content); END;
CREATE TABLE IF NOT EXISTS summaries(id INTEGER PRIMARY KEY, scope TEXT NOT NULL,
 content TEXT NOT NULL, source_ids TEXT NOT NULL, timestamp REAL NOT NULL, last_id INTEGER,
 summary_kind TEXT NOT NULL DEFAULT 'conversation');
CREATE INDEX IF NOT EXISTS summaries_scope ON summaries(scope,last_id);
CREATE TABLE IF NOT EXISTS personality(user_id INTEGER PRIMARY KEY, config TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS export_keys(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
 digest TEXT UNIQUE NOT NULL, purpose TEXT NOT NULL, expires REAL NOT NULL,
 revoked INTEGER DEFAULT 0, used INTEGER DEFAULT 0, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS web_sessions(digest TEXT PRIMARY KEY, user_id INTEGER,
 csrf TEXT NOT NULL, expires REAL NOT NULL,device_id TEXT NOT NULL DEFAULT '',
 label TEXT NOT NULL DEFAULT 'Browser',remembered INTEGER NOT NULL DEFAULT 0,
 created REAL NOT NULL DEFAULT 0,last_seen REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS web_credentials(user_id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
 salt BLOB NOT NULL, password_hash BLOB NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS access_blocks(user_id INTEGER PRIMARY KEY,created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS user_limits(user_id INTEGER PRIMARY KEY,token_limit INTEGER NOT NULL CHECK(token_limit>=0));
CREATE TABLE IF NOT EXISTS user_activity(user_id INTEGER PRIMARY KEY,started REAL,last_seen REAL,notice_at REAL,notice TEXT);
CREATE TABLE IF NOT EXISTS user_avatars(user_id INTEGER PRIMARY KEY,image BLOB,fetched REAL NOT NULL);
CREATE TABLE IF NOT EXISTS notebooks(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,title TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL);
CREATE INDEX IF NOT EXISTS notebooks_owner ON notebooks(user_id,updated);
CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,notebook_id INTEGER NOT NULL,title TEXT NOT NULL,subject TEXT NOT NULL,content TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,created REAL NOT NULL,updated REAL NOT NULL);
CREATE INDEX IF NOT EXISTS notes_owner_book ON notes(user_id,notebook_id,updated);
CREATE TABLE IF NOT EXISTS note_images(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,note_id INTEGER NOT NULL,name TEXT NOT NULL,mime TEXT NOT NULL,data BLOB NOT NULL,created REAL NOT NULL);
CREATE INDEX IF NOT EXISTS note_images_owner ON note_images(user_id,note_id);
CREATE TABLE IF NOT EXISTS workspace_state(user_id INTEGER PRIMARY KEY,notebook_id INTEGER,note_id INTEGER,scroll_y REAL NOT NULL DEFAULT 0,updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS auth_accounts(provider TEXT NOT NULL,subject TEXT NOT NULL,user_id INTEGER NOT NULL,email TEXT NOT NULL DEFAULT '',created REAL NOT NULL,PRIMARY KEY(provider,subject));
CREATE INDEX IF NOT EXISTS accounts_owner ON auth_accounts(user_id);
CREATE TABLE IF NOT EXISTS auth_flows(digest TEXT PRIMARY KEY,kind TEXT NOT NULL,expires REAL NOT NULL,payload BLOB NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,user_id INTEGER);
CREATE TABLE IF NOT EXISTS identity_settings(provider TEXT PRIMARY KEY,payload BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS audit_logs(id INTEGER PRIMARY KEY, timestamp REAL NOT NULL,
 actor_id INTEGER, action TEXT NOT NULL, target_id INTEGER, outcome TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS app_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS metrics(id INTEGER PRIMARY KEY, scope TEXT, seconds REAL, timestamp REAL);
CREATE TABLE IF NOT EXISTS token_usage(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL,
 scope TEXT NOT NULL,model TEXT NOT NULL,backend TEXT NOT NULL,input_tokens INTEGER,
 output_tokens INTEGER,timestamp REAL NOT NULL,source_message_id INTEGER);
CREATE INDEX IF NOT EXISTS usage_user_time ON token_usage(user_id,timestamp);
CREATE INDEX IF NOT EXISTS usage_time ON token_usage(timestamp);
CREATE VIEW IF NOT EXISTS profiles AS SELECT * FROM memories WHERE scope LIKE 'user:%'
 AND status='active' AND evidence='fact';
CREATE VIEW IF NOT EXISTS people AS SELECT * FROM memories WHERE category='relationship';
CREATE VIEW IF NOT EXISTS events AS SELECT * FROM memories WHERE category IN ('event','episodic');
CREATE VIEW IF NOT EXISTS preferences AS SELECT * FROM memories WHERE category='preference';
'''


@dataclass(frozen=True)
class Scope:
    kind: str
    owner: int

    def __post_init__(self):
        if self.kind not in ('user', 'group') or not isinstance(self.owner, int):
            raise ValueError('Invalid namespace')

    @property
    def key(self):
        return f'{self.kind}:{self.owner}'


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        self.db = sqlite3.connect(self.path, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=NORMAL')
        self.db.execute('PRAGMA secure_delete=ON')
        self.db.execute('PRAGMA busy_timeout=10000')
        self.db.executescript(SCHEMA)
        for table,column,definition in [('summaries','summary_kind',"TEXT NOT NULL DEFAULT 'conversation'"),
                                        ('memories','summary_id','INTEGER'),
                                        ('web_sessions','device_id',"TEXT NOT NULL DEFAULT ''"),
                                        ('web_sessions','label',"TEXT NOT NULL DEFAULT 'Browser'"),
                                        ('web_sessions','remembered','INTEGER NOT NULL DEFAULT 0'),
                                        ('web_sessions','created','REAL NOT NULL DEFAULT 0'),
                                        ('web_sessions','last_seen','REAL NOT NULL DEFAULT 0')]:
            if column not in {r[1] for r in self.db.execute('PRAGMA table_info('+table+')')}:
                self.db.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
        import secrets
        for row in self.db.execute("SELECT digest FROM web_sessions WHERE device_id=''").fetchall():
            self.db.execute('UPDATE web_sessions SET device_id=? WHERE digest=?',(secrets.token_urlsafe(12),row['digest']))
        self.db.execute('CREATE UNIQUE INDEX IF NOT EXISTS sessions_device ON web_sessions(device_id)')
        self.db.execute('CREATE INDEX IF NOT EXISTS sessions_owner ON web_sessions(user_id,expires)')
        self.db.commit()
        if not self.setting('token_tracking_since'):
            self.set_setting('token_tracking_since',time.time())
        os.chmod(self.path, 0o600)

    def rows(self, sql, args=()):
        return [dict(x) for x in self.db.execute(sql, args)]

    def execute(self, sql, args=()):
        with self.db:
            return self.db.execute(sql, args)

    def setting(self, key, default=''):
        row = self.db.execute('SELECT value FROM app_settings WHERE key=?', (key,)).fetchone()
        return row[0] if row else default

    def set_setting(self, key, value):
        self.execute('INSERT OR REPLACE INTO app_settings VALUES(?,?)', (key, str(value)))

    def register(self, user_id, name):
        self.execute('INSERT INTO users VALUES(?,?,0,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name',
                     (user_id, name[:80], time.time()))

    def allowed(self, user_id):
        row = self.db.execute('SELECT authorized FROM users WHERE id=?', (user_id,)).fetchone()
        return bool(row and row[0])

    def authorize(self, user_id, limit=20):
        if not self.allowed(user_id):
            n = self.db.execute('SELECT count(*) FROM users WHERE authorized=1').fetchone()[0]
            if n >= limit:
                raise ValueError('Limite di '+str(limit)+' utenti raggiunto.')
        self.register(user_id, self.user_name(user_id))
        self.execute('UPDATE users SET authorized=1 WHERE id=?', (user_id,))

    def user_name(self, user_id):
        row = self.db.execute('SELECT name FROM users WHERE id=?', (user_id,)).fetchone()
        return row[0] if row else str(user_id)

    def audit(self, actor, action, target=None, outcome='ok'):
        # Never put messages, arguments, keys or passwords in this table.
        self.execute('INSERT INTO audit_logs(timestamp,actor_id,action,target_id,outcome) VALUES(?,?,?,?,?)',
                     (time.time(), actor, action, target, outcome))

    def add_message(self, scope, user_id, role, content, chat_id=None, message_id=None,
                    reply_id=None, mentions=(), thread_id=0):
        self.execute('INSERT OR IGNORE INTO conversations VALUES(?,?)', (scope.key, time.time()))
        c = self.execute('''INSERT OR IGNORE INTO messages(scope,user_id,role,content,timestamp,
            telegram_chat_id,telegram_message_id,reply_id,mentions,thread_id) VALUES(?,?,?,?,?,?,?,?,?,?)''',
            (scope.key, user_id, role, content[:16000], time.time(), chat_id, message_id,
             reply_id, json.dumps(mentions), thread_id))
        return c.lastrowid if c.rowcount else None

    def recent(self, scope, limit=10, thread_id=None):
        cond, args = (' AND thread_id=?', [thread_id]) if thread_id is not None else ('', [])
        return list(reversed(self.rows('SELECT * FROM messages WHERE scope=?'+cond+' ORDER BY id DESC LIMIT ?',
                                      (scope.key, *args, min(limit, 100)))))

    def add_memory(self, scope, content, category, source_ids, evidence='fact',
                   importance=.6, confidence=1., expires=None, exportable=True):
        if category not in CATEGORIES or evidence not in ('fact', 'inference', 'uncertain') or not source_ids:
            raise ValueError('Memoria senza provenienza o categoria valida.')
        source_ids = list(dict.fromkeys(source_ids))
        sources = self.rows('SELECT * FROM messages WHERE scope=? AND id IN ('+
                           ','.join('?' for _ in source_ids)+')', (scope.key, *source_ids))
        if len(sources) != len(source_ids) or any(x['role'] != 'user' for x in sources):
            raise ValueError('Provenienza non valida per questa memoria.')
        if evidence == 'fact' and not any(content in x['content'] for x in sources):
            raise ValueError('Un fatto deve essere una citazione esatta dell’utente.')
        if scope.kind == 'user' and any(x['user_id'] != scope.owner for x in sources):
            raise ValueError('Il dato non appartiene all’utente.')
        duplicate = self.rows("SELECT id FROM memories WHERE scope=? AND content=? AND status!='deleted'",
                              (scope.key, content))
        if duplicate:
            return duplicate[0]['id']
        if evidence == 'fact' and category in ('personal','goal','preference'):
            # Preserve changes without conflating separate preferences/goals.
            def slot(text):
                text=re.sub(r'^io\s+','',text,flags=re.I)
                if re.match(r'preferisco (?:risposte )?(?:brevi|dettagliate|lunghe)\b',text,re.I): return 'response_length'
                match = re.match(r'(mi chiamo|il mio nome è|lavoro come|abito a|vivo a|il mio obiettivo è)\b',text.lower())
                if not match:
                    return None
                return {'mi chiamo':'name','il mio nome è':'name','abito a':'location','vivo a':'location',
                        'lavoro come':'job','il mio obiettivo è':'goal'}[match.group(1)]
            prefix = slot(content)
            for old in self.memories(scope, 200):
                if prefix and old['category'] == category and slot(old['content']) == prefix:
                    self.execute("UPDATE memories SET status='historical' WHERE id=?", (old['id'],))
        status = 'active' if evidence == 'fact' else 'uncertain'
        # Evidence digest is the intermediate MESSAGES -> SUMMARY -> MEMORY stage.
        digest=json.dumps([{'message_id':r['id'],'user_id':r['user_id'],'quote':r['content']} for r in sources],ensure_ascii=False)
        summary=self.execute('INSERT INTO summaries(scope,content,source_ids,timestamp,last_id,summary_kind) VALUES(?,?,?,?,?,?)',
                             (scope.key,digest,json.dumps(source_ids),time.time(),max(source_ids),'evidence')).lastrowid
        c = self.execute('''INSERT INTO memories(scope,user_id,group_id,content,category,timestamp,
             importance,confidence,status,evidence,source_ids,expires,exportable,summary_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
             (scope.key, scope.owner if scope.kind=='user' else None,
              scope.owner if scope.kind=='group' else None, content, category, time.time(),
              max(0., min(1., importance)), max(0., min(1., confidence)), status, evidence,
              json.dumps(source_ids), expires, int(exportable and scope.kind=='user'),summary))
        return c.lastrowid

    def memories(self, scope, limit=50, historical=False):
        self.execute("UPDATE memories SET status='historical' WHERE scope=? AND status IN ('active','uncertain') AND expires<=?",(scope.key,time.time()))
        statuses = "('active','uncertain','historical')" if historical else "('active','uncertain')"
        expiry = '' if historical else ' AND (expires IS NULL OR expires>?)'
        return self.rows('SELECT * FROM memories WHERE scope=? AND status IN '+statuses+
                         expiry+' ORDER BY importance DESC,id DESC LIMIT ?',
                         (scope.key, *([] if historical else [time.time()]), min(limit,500)))

    def profile(self, user_id):
        return [m for m in self.memories(Scope('user',user_id), 60) if m['evidence']=='fact']

    def tone(self, user_id):
        row = self.db.execute('SELECT config FROM personality WHERE user_id=?', (user_id,)).fetchone()
        return json.loads(row[0]) if row else PERSONALITY.copy()

    def set_tone(self, user_id, key, value):
        if key not in PERSONALITY or not 0 <= value <= 1:
            raise ValueError('Usa humor/empathy/curiosity/formality/verbosity/directness e un valore 0–1.')
        tone = self.tone(user_id)
        tone[key] = value
        self.execute('INSERT OR REPLACE INTO personality VALUES(?,?)', (user_id,json.dumps(tone)))

    def forget_memory(self, scope, memory_id):
        row = self.rows('SELECT * FROM memories WHERE id=? AND scope=?', (memory_id,scope.key))
        if not row:
            raise ValueError('Memoria non trovata in questa chat.')
        # Remove raw source too, otherwise retrieval would immediately resurrect it.
        ids = json.loads(row[0]['source_ids'])
        with self.db:
            for mid in ids:
                self.db.execute('DELETE FROM messages WHERE id=? AND scope=?', (mid,scope.key))
                self.db.execute('DELETE FROM token_usage WHERE source_message_id=? AND scope=?',(mid,scope.key))
            for m in self.rows('SELECT id,source_ids FROM memories WHERE scope=?', (scope.key,)):
                if set(json.loads(m['source_ids'])) & set(ids):
                    self.db.execute('DELETE FROM memories WHERE id=?', (m['id'],))
            self.db.execute('DELETE FROM summaries WHERE scope=?', (scope.key,))
        self.set_setting('memory_flush_cursor',0)
        self._scrub()

    def forget_user(self, user_id):
        scope = Scope('user',user_id).key
        with self.db:
            # Drop group summaries/memories which derive from this user's public messages.
            ids = {r['id'] for r in self.rows('SELECT id FROM messages WHERE user_id=?', (user_id,))}
            for table in ('memories','summaries'):
                for r in self.rows(f'SELECT id,source_ids,scope FROM {table}'):
                    if r['scope']==scope or ids & set(json.loads(r['source_ids'])):
                        self.db.execute(f'DELETE FROM {table} WHERE id=?',(r['id'],))
            self.db.execute('DELETE FROM messages WHERE scope=? OR user_id=?',(scope,user_id))
            self.db.execute('DELETE FROM conversations WHERE scope=?',(scope,))
            self.db.execute('DELETE FROM metrics WHERE scope=?',(scope,))
            self.db.execute('DELETE FROM token_usage WHERE user_id=? OR scope=?',(user_id,scope))
            for table in ('personality','export_keys','web_sessions','web_credentials','user_activity','user_limits','user_avatars','note_images','notes','notebooks','workspace_state','auth_accounts','response_feedback','memory_access_grants'):
                self.db.execute(f'DELETE FROM {table} WHERE user_id=?',(user_id,))
            self.db.execute('DELETE FROM auth_flows WHERE user_id=?',(user_id,))
            self.db.execute('DELETE FROM memory_access_grants WHERE admin_id=?',(user_id,))
            if self.db.execute("SELECT name FROM sqlite_master WHERE name='pending_updates'").fetchone():
                self.db.execute("DELETE FROM pending_updates WHERE json_extract(payload,'$.uid')=?",(user_id,))
        self.set_setting('memory_flush_cursor',0)
        self._scrub()

    def _scrub(self):
        self.db.execute("INSERT INTO memory_fts(memory_fts) VALUES('rebuild')")
        self.db.commit()
        self.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        self.db.execute('VACUUM')

    def record_tokens(self,scope,user_id,model,backend,input_tokens,output_tokens,message_id=None,timestamp=None):
        clean=lambda value: value if type(value) is int and 0<=value<2**63 else None
        self.execute('INSERT INTO token_usage(user_id,scope,model,backend,input_tokens,output_tokens,timestamp,source_message_id) VALUES(?,?,?,?,?,?,?,?)',
                     (user_id,scope.key,model,backend,clean(input_tokens),clean(output_tokens),
                      time.time() if timestamp is None else timestamp,message_id))

    def close(self):
        self.db.close()
