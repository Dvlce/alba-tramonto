"""Context-aware generation budgets. No weight changes or hidden model fallback."""
import re

CODING = re.compile(r"\b(code|function|python|javascript|typescript|sql|debug|algorithm)\b|programm|codice|script|hacking|vulnerab|algoritm", re.I)
DETAILED = re.compile(r"dettagli|approfond|passo.{0,8}passo|complet[oa]|detailed|in.depth|step.by.step|thorough", re.I)
BRIEF = re.compile(r"breve|concis|solo (?:il|la|un)|soltanto|in una frase|brief|short|just (?:the|a)|only (?:the|a)|one sentence", re.I)


def estimate(text):
    # Conservative planning estimate, not a tokenizer or a billed token count.
    # UTF-8 bytes cover non-Latin text better than character-only estimates.
    return (len(text.encode('utf-8')) + 1) // 2


def tokens(messages):
    return 32 + sum(estimate(m['content']) + 12 for m in messages)


def plan(query, ceiling=4096, context_floor=2048):
    coding = bool(CODING.search(query))
    detailed = bool(DETAILED.search(query))
    brief = bool(BRIEF.search(query))
    simple = bool(re.fullmatch(r"\s*(?:ciao|hello|hi|hey|grazie|thanks|buongiorno|buonanotte|come stai)[!?.\s]*", query, re.I))
    arithmetic = bool(re.fullmatch(r"[\s\d+*/().=?-]+", query))
    if simple or arithmetic: maximum, kind = 48, 'minimal'
    elif coding and not brief: maximum, kind = (1024 if detailed else 640), 'code'
    elif detailed and not brief: maximum, kind = 768, 'detailed'
    elif brief: maximum, kind = 96, 'brief'
    else: maximum, kind = 224, 'balanced'
    # Stable small-model context avoids resizing/reloading on every short turn.
    ceiling = max(512, min(4096, ceiling))
    context = min(ceiling, max(512, context_floor))
    if estimate(query) + maximum + 400 > context:
        context = ceiling
    maximum = min(maximum, max(48, context - 400))
    instruction = {
        'minimal': 'Risposta diretta: una frase o solo il risultato. Niente introduzioni.',
        'brief': 'Risposta breve come richiesto. Mantieni i fatti e i vincoli essenziali.',
        'balanced': 'Rispondi prima al punto. Di norma 2–5 frasi; aggiungi solo dettagli utili.',
        'code': 'Fornisci codice completo e corretto. Evita boilerplate e spiegazioni ripetute; conserva tutti i requisiti.',
        'detailed': 'La richiesta richiede dettagli: includi i passaggi e i vincoli necessari, senza ripetizioni.'
    }[kind]
    return {'kind': kind, 'coding': coding, 'output_tokens': maximum, 'context_tokens': context,
            'instruction': instruction, 'estimate_method': 'utf8-bytes/2 + message overhead'}


def assemble(system, query, history, memories, state, policy):
    import json
    maximum, context = policy['output_tokens'], policy['context_tokens']
    prompt = system + '\nSTATO E MEMORIA:\n'
    # Preserve query and instructions in full. All older turns remain in SQLite.
    from .inference import cache_friendly_messages
    def build(rows, notes):
        value = {**state, 'memories': notes, 'response_length': policy['instruction']}
        messages = [{'role': 'system', 'content': prompt + json.dumps(value, ensure_ascii=False)}]
        messages.extend({'role': r['role'], 'content': r['content']} for r in rows)
        messages.append({'role': 'user', 'content': query})
        return cache_friendly_messages(messages)
    rows = [dict(r) for r in history]
    if rows and rows[-1]['role']=='user' and rows[-1]['content']==query: rows.pop()
    notes = [{**m, 'content': m['content'][:700 if policy['coding'] else 400]} for m in memories[:4 if policy['coding'] else 2]]
    messages = build(rows, notes)
    while tokens(messages)+maximum+64 > context and rows:
        rows.pop(0)
        while rows and rows[0]['role']=='assistant': rows.pop(0)
        messages = build(rows, notes)
    while tokens(messages)+maximum+64 > context and notes:
        notes.pop(); messages = build(rows, notes)
    if tokens(messages)+maximum+64 > context:
        raise ValueError('Messaggio troppo lungo per la finestra locale. Dividilo in parti; il testo non è stato troncato.')
    return messages, {'estimated_input_tokens': tokens(messages), 'history_turns': len(rows),
                      'memories': len(notes), 'history_omitted': len(history)-len(rows),
                      'context_tokens': context, 'output_tokens': maximum, 'kind': policy['kind']}
