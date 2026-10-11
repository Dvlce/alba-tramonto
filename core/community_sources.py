"""Bounded, attributed reading from keyless public APIs; never training targets."""
import hashlib
import json
import re
import time
from urllib.parse import urlencode
from .reddit import PostText


PRESETS = (('stackoverflow', 'python'), ('jokes', 'Programming'),
           ('stackoverflow', 'javascript'), ('jokes', 'Pun'),
           ('stackoverflow', 'html'), ('jokes', 'Misc'),
           ('stackoverflow', 'css'), ('stackoverflow', 'flask'))
JOKE_CATEGORIES = ('Programming', 'Pun', 'Misc')
FLAGS = ('nsfw', 'religious', 'political', 'racist', 'sexist', 'explicit')
RETENTION = 30 * 86400


def plain(value, limit=9000):
    if not isinstance(value, str):
        return ''
    parser = PostText()
    parser.feed(value[:64000])
    return ''.join(parser.parts).strip()[:limit]


def payload(raw):
    if len(raw) > 262144:
        raise ValueError('Risposta della fonte oltre il limite.')
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ValueError('Risposta della fonte non valida.') from None
    if not isinstance(value, dict):
        raise ValueError('Risposta della fonte non valida.')
    return value


def positive(value):
    return type(value) is int and value > 0


def attribution(post):
    owner = post.get('owner')
    name = plain(owner.get('display_name', ''), 160) if isinstance(owner, dict) else ''
    uid = owner.get('user_id') if isinstance(owner, dict) else None
    author = name or 'Autore non disponibile'
    if positive(uid):
        author += ' · https://stackoverflow.com/users/' + str(uid)
    license = post.get('content_license')
    if license not in ('CC BY-SA 2.5', 'CC BY-SA 3.0', 'CC BY-SA 4.0'):
        license = 'CC BY-SA · versione nella cronologia del post'
    return author, license


def stack_entries(questions, answers):
    if not isinstance(questions, list) or not isinstance(answers, list):
        raise ValueError('Elenco Stack Overflow non valido.')
    accepted = {a['answer_id']: a for a in answers[:30] if isinstance(a, dict) and positive(a.get('answer_id'))}
    result, seen = [], set()
    for question in questions[:30]:
        if not isinstance(question, dict) or not positive(question.get('question_id')) or question.get('closed_date'):
            continue
        qid = question['question_id']
        answer = accepted.get(question.get('accepted_answer_id'))
        if qid in seen or not answer or answer.get('question_id') != qid or answer.get('is_accepted') is not True:
            continue
        title = plain(question.get('title'), 200)
        body, solution = plain(question.get('body'), 4000), plain(answer.get('body'))
        if not title or not body or not solution:
            continue
        seen.add(qid)
        qa, ql = attribution(question)
        aa, al = attribution(answer)
        url = 'https://stackoverflow.com/questions/' + str(qid)
        answer_url = 'https://stackoverflow.com/a/' + str(answer['answer_id'])
        text = ('Argomento: programmazione Python/web. Discussione pubblica; codice non verificato localmente.\n'
                'Domanda: ' + title + '\nRisposta accettata: ' + answer_url + '\n\n' + solution +
                '\n\nDomanda completa · ' + qa + '\nLicenza: ' + ql + '\nFonte: ' + url + '\n\n' + body +
                '\n\nAutore della risposta: ' + aa + '\nLicenza: ' + al + '\nFonte: ' + answer_url)
        revision = str(question.get('last_activity_date', '')) + ':' + str(answer.get('last_activity_date', ''))
        result.append({'key': str(qid), 'title': 'Stack Overflow · ' + title, 'content': text,
                       'url': answer_url, 'revision': revision, 'license': ql + ' / ' + al})
    return result


def joke_entries(value, category):
    rows = value.get('jokes', [value])
    if value.get('error') is not False or not isinstance(rows, list):
        raise ValueError('Battute non disponibili dalla fonte.')
    result, seen = [], set()
    for row in rows[:10]:
        if not isinstance(row, dict) or type(row.get('id')) is not int or row['id'] < 0 or row.get('lang') != 'en':
            continue
        flags = row.get('flags')
        if row.get('safe') is not True or not isinstance(flags, dict) or any(flags.get(flag) is not False for flag in FLAGS):
            continue
        if row.get('category') != category:
            continue
        if row.get('type') == 'twopart':
            if not all(isinstance(row.get(k), str) and row[k].strip() for k in ('setup', 'delivery')):
                continue
            body = row['setup'].strip() + '\n' + row['delivery'].strip()
        elif row.get('type') == 'single' and isinstance(row.get('joke'), str):
            body = row['joke'].strip()
        else:
            continue
        if not body or len(body) > 2500 or row['id'] in seen:
            continue
        seen.add(row['id'])
        url = 'https://v2.jokeapi.dev/joke/' + category + '?' + urlencode({'idRange': str(row['id']), 'lang': 'en', 'safe-mode': ''})
        text = 'Argomento: umorismo, humor, battute, barzellette, jokes, giochi di parole' + ('; programmazione Python/web' if category == 'Programming' else '') + '.\nFonte: JokeAPI · ' + category + ' · inglese. Adatta il gioco di parole in italiano; crea una battuta originale.\n\n' + body
        result.append({'key': 'en:' + str(row['id']), 'title': 'JokeAPI · ' + category + ' · ' + body.splitlines()[0][:160],
                       'content': text, 'url': url, 'revision': hashlib.sha256(body.encode()).hexdigest(),
                       'license': 'JokeAPI · retrieval only; no weight training'})
    return result


class CommunitySources:
    def __init__(self, knowledge):
        self.knowledge = knowledge
        self.core = knowledge.core

    def prune(self):
        rows = self.core.store.rows("SELECT id,event_id FROM core_knowledge WHERE kind IN ('stackoverflow','jokes') AND "
            "(updated<? OR id NOT IN (SELECT id FROM core_knowledge WHERE kind IN ('stackoverflow','jokes') ORDER BY updated DESC LIMIT 256))", (time.time()-RETENTION,))
        if not rows:
            return
        with self.core.store.db:
            for row in rows:
                self.core.store.db.execute('DELETE FROM core_chunks WHERE event_id=?', (row['event_id'],))
                self.core.store.db.execute('DELETE FROM core_events WHERE id=?', (row['event_id'],))
                self.core.store.db.execute('DELETE FROM core_knowledge WHERE id=?', (row['id'],))

    def snapshot(self):
        self.prune()
        stats = {r['kind']: r for r in self.core.store.rows("SELECT kind,count(*) documents,coalesce(sum(words),0) words FROM core_knowledge WHERE kind IN ('stackoverflow','jokes') GROUP BY kind")}
        return {'sources': [{**stats.get(kind, {'kind': kind, 'documents': 0, 'words': 0}), 'retry_after': float(self.core.store.setting('core_source_retry_'+kind, '0'))} for kind in ('stackoverflow', 'jokes')],
            'retention_days': 30, 'training': False, 'presets': [{'kind': k, 'query': q} for k,q in PRESETS]}

    def cooldown(self, kind, seconds):
        key = 'core_source_retry_' + kind
        self.core.store.set_setting(key, str(max(float(self.core.store.setting(key, '0')), time.time()+seconds)))

    async def stack_get(self, path, params):
        value = payload(await self.core.learning.public_get('https://api.stackexchange.com/2.3/' + path, params=params))
        backoff = value.get('backoff')
        if type(backoff) is int and backoff > 0:
            self.cooldown('stackoverflow', backoff)
        quota = value.get('quota_remaining')
        if type(quota) is int:
            self.core.store.set_setting('core_stackoverflow_quota', str(quota))
            if quota <= 0:
                self.cooldown('stackoverflow', 86400)
        if value.get('error_id') or not isinstance(value.get('items'), list):
            raise ValueError('Stack Overflow non disponibile: controlla la quota nel pannello.')
        return value['items']

    async def read(self, request):
        kind, query = request['kind'], request['query']
        self.prune()
        cache_key = 'core_source_read_' + kind + '_' + hashlib.sha256(query.casefold().encode()).hexdigest()[:24]
        cached = json.loads(self.core.store.setting(cache_key, '{}'))
        if time.time() - cached.get('time', 0) < 600:
            ids = cached.get('ids', [])
            valid = self.core.store.rows('SELECT id FROM core_knowledge WHERE kind=? AND id IN (' + ','.join('?' for _ in ids) + ')', (kind, *ids)) if ids else []
            if valid and (len(valid) >= request['count'] or cached.get('requested', 0) >= request['count']):
                return [r['id'] for r in valid][:request['count']]
        retry = float(self.core.store.setting('core_source_retry_' + kind, '0'))
        if time.time() < retry:
            raise ValueError('Fonte in pausa per la quota: riprova fra ' + str(max(1, int(retry-time.time())+1)) + ' secondi.')
        self.cooldown(kind, 60)
        try:
            if kind == 'stackoverflow':
                params = {'site': 'stackoverflow', 'pagesize': request['count'], 'filter': 'withbody', 'sort': 'votes', 'order': 'desc'}
                if re.fullmatch(r'[a-z0-9+#.-]{1,35}', query.casefold()):
                    params['tagged'] = query.casefold()
                    questions = await self.stack_get('questions', params)
                else:
                    params.update(q=query, accepted='true')
                    questions = await self.stack_get('search/advanced', params)
                ids = list(dict.fromkeys(str(q['accepted_answer_id']) for q in questions[:30] if isinstance(q, dict) and positive(q.get('accepted_answer_id'))))[:10]
                # A second, different method is allowed by Stack Exchange's per-method backoff;
                # a depleted daily quota must stop every subsequent request.
                if ids and int(self.core.store.setting('core_stackoverflow_quota', '1')) > 0:
                    answers = await self.stack_get('answers/' + ';'.join(ids), {'site': 'stackoverflow', 'filter': 'withbody', 'pagesize': 10})
                else:
                    answers = []
                rows = stack_entries(questions, answers)
            else:
                value = payload(await self.core.learning.public_get('https://v2.jokeapi.dev/joke/' + query,
                    params={'safe-mode': '', 'blacklistFlags': ','.join(FLAGS), 'lang': 'en', 'amount': request['count']}))
                rows = joke_entries(value, query)
            if not rows:
                raise ValueError('Nessun testo leggibile con questi filtri. Prova un altro argomento.')
            imported = []
            for index, row in enumerate(rows[:request['count']]):
                ident, _ = self.knowledge.remember(kind, row['key'], row['title'], row['content'], row['url'], row['revision'], row['license'])
                imported.append(ident)
                self.knowledge.advance(index+1, len(rows), row['title'])
            self.core.store.set_setting(cache_key, json.dumps({'time': time.time(), 'ids': imported, 'requested': request['count']}))
            self.prune()
            return imported
        except ValueError as exc:
            if getattr(exc, 'status', None) in (403, 429):
                self.cooldown(kind, max(600, getattr(exc, 'retry_seconds', 0)))
            raise

    def due(self):
        return (not self.knowledge.importing and not (self.knowledge.task and not self.knowledge.task.done()) and
                self.core.config['study_enabled'] and self.core.config['web_enabled'] and
                time.time()-float(self.core.store.setting('core_community_last', '0')) >= 3600 and
                any(self.core.config['connectors'].get(k) and time.time() >= float(self.core.store.setting('core_source_retry_'+k, '0')) for k in ('stackoverflow', 'jokes')))

    async def study(self):
        index = int(self.core.store.setting('core_community_topic', '0'))
        for offset in range(len(PRESETS)):
            kind, query = PRESETS[(index+offset) % len(PRESETS)]
            if not self.core.config['connectors'].get(kind) or time.time() < float(self.core.store.setting('core_source_retry_'+kind, '0')):
                continue
            self.core.store.set_setting('core_community_topic', str(index+offset+1))
            self.core.store.set_setting('core_community_last', str(time.time()))
            imported = await self.knowledge.import_sources({'kind': kind, 'query': query, 'count': 6})
            if not imported:
                raise ValueError(self.knowledge.progress.get('detail', 'Nessuna fonte disponibile.'))
            break
