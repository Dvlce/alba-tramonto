"""Extractive memory: exact user quotes, never an LLM-created fact."""
import json
import re
import time
import unicodedata
from store import Scope

STOP = set('il lo la i gli le un una uno di da a e o che è sono per con su del della mi ti si non io tu cosa come quando ricordare ricordi ricorda mio mia miei mie'.split())
SYNONYMS = {'lavoro':['lavoro','lavorare','professione'], 'lavorare':['lavoro','lavorare'],
            'obiettivi':['obiettivo','vorrei'], 'obiettivo':['obiettivo','vorrei'],
            'interessi':['piace','preferisco'], 'preferenze':['preferisco','piace'],
            'nome':['chiamo','nome'], 'relazioni':['moglie','marito','amico','compagna','compagno'],
            'abito':['abito','vivo'], 'residenza':['abito','vivo']}
RULES = [(r'mi chiamo\b|il mio nome è\b|(?:io )?(?:lavoro come|abito a|vivo a|ho \d+ anni)\b','personal'),
         (r'(?:mi piace|preferisco|mi interessa)\b','preference'),
         (r'(?:il mio obiettivo è|vorrei riuscire a|sto studiando per|sto preparando|devo sostenere|(?:voglio|vorrei|devo|ho intenzione di) (?:pubblicare|creare|sviluppare|finire|completare|imparare|prendere|studiare|andare avanti))\b','goal'),
         (r'(?:mia moglie|mio marito|il mio compagno|la mia compagna|mio figlio|mia figlia|il mio amico|mia madre|mio padre|mia sorella|mio fratello)\b','relationship'),
         (r'(?:oggi ho|ieri ho|domani ho|il \d{1,2}[ /])\b','event')]


def terms(text):
    text = ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if not unicodedata.combining(c))
    return [w for w in re.findall(r'[a-z0-9]+', text) if len(w)>2 and w not in STOP][:24]


def retrieve(store, scope, query, limit=8):
    words = terms(query)
    expanded = list(dict.fromkeys(w for term in words for w in SYNONYMS.get(term,[term])))[:32]
    if not expanded:
        return []
    # Only letters/digits survive terms(): user text cannot become SQL or FTS syntax.
    expression = ' OR '.join('"'+w+'"*' for w in expanded)
    rows = store.rows('''SELECT m.*,bm25(memory_fts) AS rank FROM memory_fts
         JOIN memories m ON m.id=memory_fts.rowid WHERE memory_fts MATCH ? AND m.scope=?
         AND m.status IN ('active','uncertain') AND (m.expires IS NULL OR m.expires>?)
         ORDER BY rank LIMIT 40''',(expression,scope.key,time.time()))
    def score(m):
        overlap = len(set(expanded) & set(terms(m['content'])))
        return overlap + m['importance']*.4 + m['confidence']*.2 + .1/(1+(time.time()-m['timestamp'])/86400)
    return sorted(rows,key=score,reverse=True)[:limit]


def relevant_messages(store, scope, query, limit=3):
    words = terms(query)
    if not words:
        return []
    clauses = ' OR '.join('content LIKE ?' for _ in words[:8])
    return store.rows('SELECT * FROM messages WHERE scope=? AND role=\'user\' AND ('+clauses+
                      ') ORDER BY id DESC LIMIT ?', (scope.key,*['%'+w+'%' for w in words[:8]],limit))


def summarize(store, scope, force=False):
    last = store.rows("SELECT last_id FROM summaries WHERE scope=? AND summary_kind='conversation' ORDER BY id DESC LIMIT 1",(scope.key,))
    last_id = last[0]['last_id'] if last else 0
    rows = store.rows("SELECT * FROM messages WHERE scope=? AND id>? AND role='user' ORDER BY id LIMIT 20",
                      (scope.key,last_id))
    if not rows or (len(rows)<12 and not force):
        return
    # An extractive digest, each item has a verifiable source and author.
    content = json.dumps([{'message_id':r['id'], 'user_id':r['user_id'],
                           'quote':r['content'][:180]} for r in rows],ensure_ascii=False)
    store.execute('INSERT INTO summaries(scope,content,source_ids,timestamp,last_id) VALUES(?,?,?,?,?)',
                   (scope.key,content,json.dumps([r['id'] for r in rows]),time.time(),rows[-1]['id']))


def memory_candidates(text):
    # Do not learn personal claims from quotations, forwarded material, questions or instructions.
    if text.startswith('/') or any(x in text for x in ('?', '>')):
        return []
    candidates = []
    for sentence in re.split(r'[\n.!;]+|\s+e\s+(?=(?:mi piace|preferisco|il mio obiettivo|voglio imparare)\b)',text,flags=re.I):
        sentence = sentence.strip()
        sentence=re.sub(r'^(?:(?:secondo te|diciamo|beh|sai|allora)[ ,]+)+','',sentence,flags=re.I)
        if not 8 <= len(sentence) <= 500:
            continue
        # Quoted speech is masked for detection; exact original wording remains the source.
        declaration=re.sub(r'«[^»]*»|"[^"]*"|“[^”]*”',' ',sentence)
        uncertain = bool(re.search(r'\b(?:forse|ipotizzo|probabilmente|non so se|potrebbe|credo che|mi sembra|non sono sicuro)\b',sentence,re.I))
        for pattern, category in RULES:
            # Anchor first-person assertions; "Mario dice che mi chiamo X" is not a fact about sender.
            if re.match('(?:forse |probabilmente )?(?:io )?(?:'+pattern+')',declaration,re.I):
                expires = time.time()+7*86400 if re.match(r'(?:oggi|ieri|domani)',sentence,re.I) else None
                candidates.append(dict(content=sentence,category='temporary' if expires else category,
                                       evidence='uncertain' if uncertain else 'fact',
                                       confidence=.5 if uncertain else 1.,importance=.7,expires=expires))
                break
    return candidates


def evaluate_memories(store, scope, message_id):
    row = store.rows('SELECT * FROM messages WHERE id=? AND scope=? AND role=\'user\'',(message_id,scope.key))
    if not row:
        return []
    created=[]
    for candidate in memory_candidates(row[0]['content']):
        if scope.kind=='group':
            candidate['category']='group'
        created.append(store.add_memory(scope,source_ids=[message_id],**candidate))
    summarize(store,scope)
    return created


def build_context(store, scope, query, budget=7000, thread_id=0):
    memories = retrieve(store,scope,query)
    # No user profile or personal tone is loaded for a group request.
    profile = store.profile(scope.owner)[:8] if scope.kind=='user' else []
    merged = {m['id']:m for m in memories+profile}
    data = {'namespace':scope.key,'memories':[], 'recent':[], 'relevant':[], 'summaries':[]}
    def append(section,item):
        data[section].append(item)
        if len(json.dumps(data,ensure_ascii=False))>budget:
            data[section].pop()
            return False
        return True
    # Reserve space for the current exchange before adding older profile material.
    recent = store.recent(scope,8,thread_id)
    for r in reversed(recent):
        append('recent',{'id':r['id'],'user_id':r['user_id'],'role':r['role'],'content':r['content'][:650],
                         'reply_id':r['reply_id']})
    data['recent'].reverse()
    for m in merged.values():
        item={k:m[k] for k in ('id','content','category','evidence','status','source_ids')}
        ids=json.loads(m['source_ids'])
        authors=store.rows('SELECT DISTINCT user_id FROM messages WHERE scope=? AND id IN ('+
                          ','.join('?' for _ in ids)+')',(scope.key,*ids))
        item['authors']=[r['user_id'] for r in authors]
        append('memories',item)
    for r in relevant_messages(store,scope,query):
        append('relevant',{'id':r['id'],'user_id':r['user_id'],'quote':r['content'][:500]})
    for s in store.rows("SELECT content FROM summaries WHERE scope=? AND summary_kind='conversation' ORDER BY id DESC LIMIT 1",(scope.key,)):
        append('summaries',json.loads(s['content']))
    for s in store.rows("SELECT content FROM summaries WHERE scope=? AND summary_kind='consolidated' ORDER BY id DESC LIMIT 1",(scope.key,)):
        append('summaries',json.loads(s['content']))
    return data
