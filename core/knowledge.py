"""Persistent, immediately searchable lessons and bounded public-source imports.

Retrieved documents are data, never commands. Network reads use only the public
Wikipedia and GitHub APIs and public Reddit RSS; source text is not executable.
"""
import asyncio
import base64
import hashlib
import json
import re
import time
from urllib.parse import quote, urlsplit, unquote
from .reddit import subreddit_name, reddit_entries, humor_request, COMMUNITIES, HUMOR, RSS_NOTICE, RSS_END, RETENTION_SECONDS


TOPICS = ('Lingua italiana', 'Python (linguaggio di programmazione)', 'JavaScript',
          'HTML', 'CSS', 'HTTP', 'Git', 'Programmazione asincrona')
STOPWORDS = set('come cosa quale quali della delle degli dello sono essere questo questa quello quella vorrei sapere spiegami spiega per con una uno che and the what explain about'.split())
LANGUAGE_CODE = r'[a-z]{2,12}(?:-[a-z]{2,12}){0,2}'


def words(text):
    return len(re.findall(r"\b[\w]+(?:['’][\w]+)?\b", text, re.UNICODE))


def source_request(value):
    if not isinstance(value, dict) or set(value) - {'kind', 'query', 'language', 'count'}:
        raise ValueError('Fonte non valida.')
    kind = value.get('kind')
    query = value.get('query')
    if kind not in ('wikipedia', 'github', 'reddit') or not isinstance(query, str) or not 1 <= len(query.strip()) <= 200:
        raise ValueError('Indica un argomento Wikipedia, un repository pubblico o un subreddit.')
    language = value.get('language', 'it')
    if not isinstance(language, str) or not re.fullmatch(LANGUAGE_CODE, language):
        raise ValueError('Lingua Wikipedia non valida.')
    count = value.get('count', 1)
    if type(count) is not int or not 1 <= count <= (12 if kind == 'reddit' else 3):
        raise ValueError('Importa da 1 a 12 post Reddit oppure da 1 a 3 articoli per volta.')
    query = query.strip()
    if kind == 'reddit':
        query = subreddit_name(query)
    elif kind == 'github':
        from .learning import repo_name
        query = repo_name(query)
    elif '://' in query:
        parsed = urlsplit(query)
        if (parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port or
                not re.fullmatch(LANGUAGE_CODE+r'\.wikipedia\.org', parsed.hostname or '') or
                not parsed.path.startswith('/wiki/') or parsed.query or parsed.fragment):
            raise ValueError('Usa un argomento o un link https://lingua.wikipedia.org/wiki/Articolo.')
        language = parsed.hostname.split('.')[0]
        query = unquote(parsed.path[6:]).replace('_', ' ')
        if not 1 <= len(query) <= 200:
            raise ValueError('Titolo Wikipedia troppo lungo.')
    return {'kind': kind, 'query': query, 'language': language, 'count': count}


class Knowledge:
    def __init__(self, core):
        self.core = core
        self.task = None
        self.importing = False
        self.progress = {}
        self.lookup_cache = {}
        core.store.db.executescript('''
          CREATE TABLE IF NOT EXISTS core_knowledge(
            id INTEGER PRIMARY KEY,kind TEXT NOT NULL,source_key TEXT NOT NULL,
            title TEXT NOT NULL,url TEXT NOT NULL,revision TEXT NOT NULL,license TEXT NOT NULL,
            content TEXT NOT NULL,words INTEGER NOT NULL,digest TEXT NOT NULL,
            event_id INTEGER NOT NULL,created REAL NOT NULL,updated REAL NOT NULL,
            UNIQUE(kind,source_key));
          CREATE INDEX IF NOT EXISTS core_knowledge_event ON core_knowledge(event_id);
          CREATE TABLE IF NOT EXISTS core_teaching(
            id INTEGER PRIMARY KEY,knowledge_id INTEGER NOT NULL,prompt TEXT NOT NULL,
            answer TEXT NOT NULL,created REAL NOT NULL,UNIQUE(knowledge_id,prompt));
          CREATE TABLE IF NOT EXISTS core_source_jobs(
            id INTEGER PRIMARY KEY,request TEXT NOT NULL,status TEXT NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0,total INTEGER NOT NULL DEFAULT 1,
            detail TEXT NOT NULL DEFAULT '',started REAL NOT NULL,finished REAL);
        ''')
        core.store.execute("UPDATE core_source_jobs SET status='interrupted',finished=?,detail='Importazione interrotta dal riavvio' WHERE status='running'", (time.time(),))

    def remember(self, kind, key, title, content, url='', revision='', license=''):
        content = content.strip()[:64000]
        if not content:
            raise ValueError('Il documento è vuoto.')
        digest = hashlib.sha256(content.encode()).hexdigest()
        old = self.core.store.rows('SELECT * FROM core_knowledge WHERE kind=? AND source_key=?', (kind, key))
        if old and old[0]['digest'] == digest:
            self.core.store.execute('UPDATE core_knowledge SET updated=?,revision=?,license=? WHERE id=?',
                                    (time.time(), revision, license, old[0]['id']))
            return old[0]['id'], False
        category = {'wikipedia': 'web', 'github': 'github', 'teacher': 'files', 'reddit': 'reddit'}[kind]
        # One stable event per source avoids growing duplicate memories on refresh.
        event = old[0]['event_id'] if old else self.core.event(category, 'source', title+'\n'+content[:11000])
        now = time.time()
        with self.core.store.db:
            self.core.store.db.execute('UPDATE core_events SET content=?,created=? WHERE id=?',
                                      ((title+'\n'+url+'\n'+content)[:12000], now, event))
            self.core.store.db.execute('DELETE FROM core_chunks WHERE event_id=?', (event,))
            for part, offset in enumerate(range(0, len(content), 780)):
                self.core.store.db.execute('INSERT INTO core_chunks(event_id,part,content,embedding,model) VALUES(?,?,?,?,?)',
                                          (event, part, title+'\n'+content[offset:offset+900], None, self.core.config['embedding_model']))
            self.core.store.db.execute('''INSERT INTO core_knowledge(kind,source_key,title,url,revision,license,content,words,digest,event_id,created,updated)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(kind,source_key) DO UPDATE SET
                title=excluded.title,url=excluded.url,revision=excluded.revision,license=excluded.license,
                content=excluded.content,words=excluded.words,digest=excluded.digest,updated=excluded.updated''',
                (kind, key, title[:240], url, revision, license, content, words(content), digest, event, now, now))
        ident = self.core.store.rows('SELECT id FROM core_knowledge WHERE kind=? AND source_key=?', (kind, key))[0]['id']
        return ident, True

    def teach(self, value):
        if not isinstance(value, dict) or set(value) - {'title', 'text', 'question', 'answer'}:
            raise ValueError('Lezione non valida.')
        title, text = value.get('title', ''), value.get('text', '')
        question, answer = value.get('question', ''), value.get('answer', '')
        if not all(isinstance(x, str) for x in (title, text, question, answer)):
            raise ValueError('La lezione deve contenere testo.')
        if not 1 <= len(title.strip()) <= 160 or not 1 <= len(text.strip()) <= 32000:
            raise ValueError('Titolo obbligatorio (160 caratteri), testo da 1 a 32.000 caratteri.')
        if bool(question.strip()) != bool(answer.strip()) or len(question) > 600 or len(answer) > 1600:
            raise ValueError('Per il training aggiungi sia domanda (600 caratteri) sia risposta ideale (1.600 caratteri).')
        key = hashlib.sha256(title.strip().casefold().encode()).hexdigest()
        ident, changed = self.remember('teacher', key, title.strip(), text, license='owner-provided')
        if question.strip():
            self.core.store.execute('''INSERT INTO core_teaching(knowledge_id,prompt,answer,created) VALUES(?,?,?,?)
                ON CONFLICT(knowledge_id,prompt) DO UPDATE SET answer=excluded.answer,created=excluded.created''',
                (ident, question.strip(), answer.strip(), time.time()))
        self.core.event('training', 'lesson_saved', json.dumps({'id': ident, 'words': words(text), 'training_pair': bool(question.strip()), 'changed': changed}))
        return {'id': ident, 'words': words(text), 'changed': changed, 'training_pair': bool(question.strip())}

    def retrieve(self, query, limit=3):
        self.prune_reddit()
        terms = list(dict.fromkeys(w for w in re.findall(r'\w+', query.casefold()) if len(w) > 2 and w not in STOPWORDS))[:10]
        humor = humor_request(query)
        if humor:
            terms.append('humor')
        active = [kind for kind, category in (('teacher', 'files'), ('wikipedia', 'web'), ('github', 'github'), ('reddit', 'reddit')) if self.core.config['connectors'].get(category)]
        if not terms or not active:
            return []
        rows = self.core.store.rows('SELECT k.id,k.kind,k.title,k.url,k.event_id,c.content FROM core_knowledge k '
            'JOIN core_chunks c ON c.event_id=k.event_id WHERE k.kind IN ('+','.join('?' for _ in active)+') AND ('+
            ' OR '.join('lower(c.content) LIKE ?' for _ in terms)+') ORDER BY k.updated DESC,c.part LIMIT 3000', (*active, *('%'+w+'%' for w in terms)))
        def score(row):
            tokens = set(re.findall(r'\w+', row['content'].casefold()))
            matched = sum(w in tokens for w in terms)
            return matched * 5 + sum(w in row['title'].casefold() for w in terms) + (10 if humor and row['kind']=='reddit' and 'humor' in tokens else 0)
        rows.sort(key=score, reverse=True)
        selected = []
        for row in rows:
            if score(row) and not any(x['source'] == row['event_id'] for x in selected):
                selected.append({'source': row['event_id'], 'category': {'teacher': 'files', 'wikipedia': 'web', 'github': 'github', 'reddit': 'reddit'}[row['kind']],
                                 'title': row['title'], 'url': row['url'], 'content': row['content']})
            if len(selected) >= limit:
                break
        return selected

    def snapshot(self):
        self.prune_reddit()
        stats = self.core.store.rows('SELECT count(*) documents,coalesce(sum(words),0) words FROM core_knowledge')[0]
        indexed = self.core.store.rows('SELECT count(*) n FROM core_knowledge k WHERE EXISTS(SELECT 1 FROM core_chunks c WHERE c.event_id=k.event_id)')[0]['n']
        sources = self.core.store.rows('SELECT id,kind,title,url,revision,license,words,updated FROM core_knowledge ORDER BY updated DESC LIMIT 50')
        pairs = self.core.store.rows('SELECT count(*) n FROM core_teaching')[0]['n']
        return {**stats, 'indexed': indexed, 'indexed_percent': round(indexed/stats['documents']*100, 1) if stats['documents'] else None,
                'teaching_pairs': pairs, 'sources': sources, 'running': self.importing or bool(self.task and not self.task.done()),
                'manual_running': bool(self.task and not self.task.done()),
                'progress': self.progress, 'jobs': self.core.store.rows('SELECT * FROM core_source_jobs ORDER BY id DESC LIMIT 12'),
                'focus': 'Italiano, programmazione Python/web e umorismo',
                'reddit': {'communities': [{'name': n, 'topic': t} for n,t in COMMUNITIES],
                    'documents': sum(r['documents'] for r in self.core.store.rows("SELECT count(*) documents FROM core_knowledge WHERE kind='reddit'")),
                    'words': self.core.store.rows("SELECT coalesce(sum(words),0) words FROM core_knowledge WHERE kind='reddit'")[0]['words'],
                    'rss_end': RSS_END, 'notice_url': RSS_NOTICE, 'retention_days': 7, 'training': False}}

    def start(self, value):
        request = source_request(value)
        if self.importing or self.task and not self.task.done():
            raise ValueError('Una raccolta di fonti è già in corso.')
        self.check_enabled(request['kind'])
        self.task = asyncio.create_task(self.import_sources(request))

    def check_enabled(self, kind):
        category = {'wikipedia':'web', 'github':'github', 'reddit':'reddit'}[kind]
        if not self.core.config['web_enabled'] or not self.core.config['connectors'].get(category):
            raise ValueError('Abilita la ricerca web e il relativo connettore.')

    async def stop(self):
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)

    async def import_sources(self, request):
        request = source_request(request)
        self.check_enabled(request['kind'])
        if self.importing:
            raise ValueError('Una raccolta di fonti è già in corso.')
        self.importing = True
        job = self.core.store.execute('INSERT INTO core_source_jobs(request,status,total,started) VALUES(?,?,?,?)',
                                     (json.dumps(request), 'running', request['count'], time.time())).lastrowid
        self.progress = {'id': job, 'completed': 0, 'total': request['count'], 'percent': 0, 'detail': 'Connessione alla fonte pubblica'}
        try:
            imported = await {'wikipedia':self.wikipedia, 'github':self.github, 'reddit':self.reddit}[request['kind']](request)
            self.advance(len(imported), len(imported), 'Fonti indicizzate')
            self.core.store.execute("UPDATE core_source_jobs SET status='ready',completed=total,finished=?,detail=? WHERE id=?",
                                    (time.time(), str(len(imported))+' documenti indicizzati; fonti e revisioni conservate', job))
            self.progress.update(completed=self.progress['total'], percent=100, detail='Fonti indicizzate e disponibili nella chat')
            return imported
        except asyncio.CancelledError:
            self.core.store.execute("UPDATE core_source_jobs SET status='interrupted',finished=?,detail='Importazione interrotta' WHERE id=?", (time.time(), job))
            self.progress['detail'] = 'Importazione interrotta'
            raise
        except Exception as exc:
            self.core.store.execute("UPDATE core_source_jobs SET status='error',finished=?,detail=? WHERE id=?", (time.time(), str(exc)[:800], job))
            self.progress['detail'] = str(exc)[:800]
            self.core.event('reddit' if request['kind']=='reddit' else 'web', 'error', 'Apprendimento: '+str(exc)[:800])
            return []
        finally:
            self.importing = False

    def prune_reddit(self):
        # A bounded, short-lived reading cache, never a permanent training corpus.
        expired = self.core.store.rows("SELECT id,event_id,url FROM core_knowledge WHERE kind='reddit' AND "
            "(updated<? OR id NOT IN (SELECT id FROM core_knowledge WHERE kind='reddit' ORDER BY updated DESC LIMIT 192))", (time.time()-RETENTION_SECONDS,))
        with self.core.store.db:
            self.core.store.db.execute('DELETE FROM core_reddit WHERE created<?', (time.time()-RETENTION_SECONDS,))
            for row in expired:
                self.core.store.db.execute('DELETE FROM core_chunks WHERE event_id=?', (row['event_id'],))
                self.core.store.db.execute('DELETE FROM core_events WHERE id=?', (row['event_id'],))
                self.core.store.db.execute('DELETE FROM core_knowledge WHERE id=?', (row['id'],))
                self.core.store.db.execute('DELETE FROM core_reddit WHERE url=?', (row['url'],))

    async def reddit(self, request):
        group = request['query']
        now = time.time()
        if now >= RSS_END:
            raise ValueError('Reddit ha annunciato la fine dei feed RSS dal 13 novembre 2026. Serve un accesso approvato dalla piattaforma per nuove letture.')
        self.prune_reddit()
        last = float(self.core.store.setting('core_reddit_read_'+group, '0'))
        if now-last < 600:
            cached = self.core.store.rows("SELECT id FROM core_knowledge WHERE kind='reddit' AND source_key LIKE ? ORDER BY updated DESC LIMIT ?", (group+':%', request['count']))
            if cached:
                return [r['id'] for r in cached]
            raise ValueError('Feed Reddit già richiesto: attendi 10 minuti prima di riprovare.')
        self.core.store.set_setting('core_reddit_read_'+group, str(now))
        try:
            raw = await self.core.learning.public_get('https://www.reddit.com/r/'+group+'/.rss')
            rows = reddit_entries(raw, group)[:request['count']]
            if not rows:
                raise ValueError('Nessun post leggibile nel feed pubblico di r/'+group+'. Il subreddit può essere privato, vuoto o senza contenuti testuali.')
            self.advance(0, len(rows), 'Lettura di r/'+group)
            topic = 'Umorismo, humor, battute, barzellette, jokes, giochi di parole' if group in HUMOR else 'Programmazione Python/web' if group in {n for n,t in COMMUNITIES if t=='programming'} else 'Discussioni pubbliche'
            imported = []
            for index, row in enumerate(rows):
                text = 'Argomento: '+topic+'. Fonte pubblica non verificata.\n\n'+row['title']+'\n\n'+row['excerpt']
                ident, _ = self.remember('reddit', group+':'+row['id'], 'r/'+group+' · '+row['title'], text,
                    row['url'], row['revision'], 'Reddit user content · retrieval only')
                self.core.store.execute('''INSERT INTO core_reddit(url,subreddit,title,excerpt,created) VALUES(?,?,?,?,?)
                    ON CONFLICT(url) DO UPDATE SET title=excluded.title,excerpt=excluded.excerpt,created=excluded.created''',
                    (row['url'], group, row['title'], row['excerpt'], now))
                imported.append(ident)
                self.advance(index+1, len(rows), 'r/'+group+' · '+row['title'])
            self.prune_reddit()
            return imported
        finally:
            self.core.config['last_reddit'] = time.time()
            self.core.save()

    def advance(self, completed, total, detail):
        self.progress.update(completed=completed, total=total, percent=round(completed/total*100), detail=detail)
        self.core.store.execute('UPDATE core_source_jobs SET completed=?,total=?,detail=? WHERE id=?',
                                (completed, total, detail[:800], self.progress['id']))

    async def wikipedia(self, request):
        endpoint = 'https://'+request['language']+'.wikipedia.org/w/api.php'
        raw = await self.core.learning.public_get(endpoint, params={'action': 'query', 'format': 'json', 'formatversion': 2,
            'list': 'search', 'srsearch': request['query'], 'srlimit': request['count']})
        hits = json.loads(raw).get('query', {}).get('search', [])
        if not hits:
            raise ValueError('Nessun articolo Wikipedia trovato.')
        self.advance(0, len(hits), 'Lettura degli articoli Wikipedia')
        imported = []
        for index, hit in enumerate(hits):
            raw = await self.core.learning.public_get(endpoint, limit=1500000, params={'action': 'query', 'format': 'json', 'formatversion': 2,
                'pageids': hit['pageid'], 'prop': 'extracts|info|revisions', 'explaintext': 1, 'exsectionformat': 'plain',
                'inprop': 'url', 'rvprop': 'ids', 'rvlimit': 1})
            page = json.loads(raw).get('query', {}).get('pages', [{}])[0]
            text = page.get('extract', '').strip()
            if words(text) < 20:
                raise ValueError('Articolo senza testo utilizzabile: '+hit['title'])
            url = page.get('fullurl') or 'https://'+request['language']+'.wikipedia.org/wiki/'+quote(page['title'].replace(' ', '_'))
            revision = str(page.get('revisions', [{}])[0].get('revid', ''))
            ident, _ = self.remember('wikipedia', request['language']+':'+str(page['pageid']), page['title'], text, url, revision, 'CC BY-SA · Wikipedia')
            imported.append(ident)
            self.advance(index+1, len(hits), page['title'])
        return imported

    async def github(self, request):
        repo = request['query']
        endpoint = 'https://api.github.com/repos/'+repo
        metadata = json.loads(await self.core.learning.public_get(endpoint))
        if metadata.get('private'):
            raise ValueError('Sono disponibili solo repository pubblici.')
        branch = metadata.get('default_branch', 'main')
        commit = json.loads(await self.core.learning.public_get(endpoint+'/commits/'+quote(branch, safe='')))
        sha = commit.get('sha', '')
        if not re.fullmatch(r'[a-f0-9]{40}', sha):
            raise ValueError('Revisione GitHub non valida.')
        prefix=repo+'/'
        cached=self.core.store.rows('SELECT id,revision FROM core_knowledge WHERE kind=? AND substr(source_key,1,?)=?',('github',len(prefix),prefix))
        if cached and all(row['revision']==sha for row in cached):
            self.advance(len(cached),len(cached),'Revisione già indicizzata: '+sha[:7])
            return [row['id'] for row in cached]
        tree = json.loads(await self.core.learning.public_get(endpoint+'/git/trees/'+sha, limit=6000000, params={'recursive': '1'}))
        entries = [entry for entry in tree.get('tree', []) if entry.get('type') == 'blob' and
            0 < entry.get('size', 0) <= 64000 and re.search(r'\.(md|rst|txt|py|js|ts|html|css)$', entry.get('path', ''), re.I) and
            not any(part.startswith('.') or part in ('vendor', 'node_modules', 'dist', 'build', 'venv', 'tests') for part in entry['path'].split('/'))]
        entries.sort(key=lambda e: (0 if e['path'].casefold().startswith('readme') else 1 if e['path'].startswith('docs/') else 2,
                                    e['path'].count('/'), e['path']))
        entries = entries[:6]
        if not entries:
            raise ValueError('Nessun documento testuale nel repository pubblico.')
        license = (metadata.get('license') or {}).get('spdx_id', 'NOASSERTION')
        self.advance(0, len(entries), 'Lettura dei documenti GitHub alla revisione '+sha[:7])
        imported = []
        for index, entry in enumerate(entries):
            raw = json.loads(await self.core.learning.public_get(endpoint+'/git/blobs/'+entry['sha'], limit=150000))
            if raw.get('encoding') != 'base64':
                raise ValueError('Formato del file GitHub non supportato.')
            text = base64.b64decode(raw.get('content', ''), validate=False).decode('utf-8', errors='replace')
            ident, _ = self.remember('github', repo+'/'+entry['path'], repo+' · '+entry['path'], text,
                'https://github.com/'+repo+'/blob/'+sha+'/'+quote(entry['path'], safe='/'), sha, license)
            imported.append(ident)
            self.advance(index+1, len(entries), entry['path'])
        return imported

    async def refresh_next(self):
        if self.importing or self.task and not self.task.done() or not self.core.config['web_enabled'] or not self.core.config['connectors']['web']:
            return
        index = int(self.core.store.setting('core_knowledge_topic', '0'))
        self.core.store.set_setting('core_knowledge_topic', str(index+1))
        await self.import_sources({'kind': 'wikipedia', 'query': TOPICS[index % len(TOPICS)], 'language': 'it', 'count': 1})

    async def lookup(self, query):
        if not self.core.config.get('online_lookup', True) or not self.core.config['web_enabled'] or self.importing or self.task and not self.task.done():
            return
        if not re.search(r'wikipedia|github|\bcerca\b|\bchi è\b|cos[’\x27]?è|che cos|spieg|parlami|come funziona', query, re.I):
            return
        if re.search(r'\b(password|secret|token|apikey|account|mio|mia|miei|mie|nostro|nostra|quaderno|chat)\b|[\w.+-]+@[\w.-]+',query,re.I):
            return
        key = query.casefold()[:200]
        if time.time()-self.lookup_cache.get(key, 0) < 600:
            return
        self.lookup_cache[key] = time.time()
        if len(self.lookup_cache) > 100:
            self.lookup_cache.pop(next(iter(self.lookup_cache)))
        match = re.search(r'(?:https://github\.com/|github\s+)([\w.-]+/[\w.-]+)', query, re.I)
        reddit = re.search(r'(?:https://(?:www\.)?reddit\.com/)?\br/([A-Za-z0-9_]{2,21})\b', query, re.I)
        value = {'kind':'reddit','query':reddit[1],'count':3} if reddit else {'kind': 'github', 'query': match[1]} if match else {'kind': 'wikipedia', 'query': query[:180], 'language': 'it', 'count': 1}
        try:
            self.check_enabled(value['kind'])
            await asyncio.wait_for(self.import_sources(value), 20)
        except (ValueError, asyncio.TimeoutError):
            pass

    def training_examples(self):
        rows = [{'prompt': r['prompt'], 'answer': r['answer'], 'origin': 'owner-taught', 'source_id': r['knowledge_id'], 'task': 'language'}
                for r in self.core.store.rows('SELECT * FROM core_teaching ORDER BY created DESC LIMIT 32')]
        # Document-grounded rehearsal: use short attributed prose, not generated
        # answers or unverified source code. Full documents remain retrieval data.
        for source in self.core.store.rows("SELECT * FROM core_knowledge WHERE kind IN ('wikipedia','github') ORDER BY updated DESC LIMIT 32"):
            if source['kind'] == 'github' and (source['license'] not in ('MIT', 'Apache-2.0', 'BSD-2-Clause', 'BSD-3-Clause') or not re.search(r'\.(md|rst|txt)$', source['title'], re.I)):
                continue
            paragraphs = re.sub(r'```.*?```', '', source['content'], flags=re.S).split('\n\n')
            prose = next((re.sub(r'\s+', ' ', p).strip() for p in paragraphs if words(p) >= 25 and not p.lstrip().startswith(('#', '<', '|', '..'))), '')
            if not prose:
                continue
            answer = ' '.join(prose.split()[:80])
            italian = source['kind'] == 'wikipedia' and source['source_key'].startswith('it:')
            rows.append({'prompt': ('Descrivi brevemente ' if italian else 'Briefly describe ')+source['title']+'.', 'answer': answer, 'origin': 'public-document',
                         'system': 'Sei Notte. Descrivi i fatti nella lingua della fonte.' if italian else 'You are Notte. Describe the facts faithfully in the language of the source.',
                         'task': 'language', 'source_id': source['id'], 'url': source['url'], 'revision': source['revision'], 'license': source['license']})
            if sum(r['origin'] == 'public-document' for r in rows) >= 12:
                break
        return rows
