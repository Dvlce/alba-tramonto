"""Owner-scoped explicit feedback changes response style, never factual memory or model weights."""
import time
from store import Scope
LABELS={'utile','ripetitiva','fuori_tema','piu_concreta','troppo_lunga'}
INSTRUCTIONS={'ripetitiva':'Avanza rispetto alle risposte precedenti ed evita domande già poste.',
 'fuori_tema':'Rimani sul tema dell’ultimo messaggio; evita esempi non pertinenti.',
 'piu_concreta':'Se viene chiesto aiuto, proponi un passo concreto e praticabile.',
 'troppo_lunga':'Preferisci risposte brevi, conservando le informazioni necessarie.'}
def record_feedback(store,uid,label,message_id=None):
    if not isinstance(label,str) or label not in LABELS: raise ValueError('Usa utile, ripetitiva, fuori_tema, piu_concreta oppure troppo_lunga.')
    scope=Scope('user',uid).key
    rows=store.rows('SELECT id FROM messages WHERE scope=? AND role=\'assistant\''+(' AND id=?' if message_id is not None else '')+' ORDER BY id DESC LIMIT 1', (scope,message_id) if message_id is not None else (scope,))
    if not rows: raise PermissionError('La risposta deve appartenere alla tua conversazione privata.')
    store.execute('INSERT INTO response_feedback VALUES(?,?,?,?) ON CONFLICT(user_id,message_id) DO UPDATE SET label=excluded.label,timestamp=excluded.timestamp',(uid,rows[0]['id'],label,time.time()))
    store.audit(uid,'feedback_'+label,uid)
def feedback_instruction(store,uid):
    rows=store.rows('SELECT label FROM response_feedback WHERE user_id=? ORDER BY timestamp DESC LIMIT 30',(uid,))
    counts={key:sum(r['label']==key for r in rows) for key in INSTRUCTIONS}
    return 'Preferenze esplicite sul modo di rispondere: '+' '.join(INSTRUCTIONS[key] for key,count in counts.items() if count>=2) if any(count>=2 for count in counts.values()) else ''
