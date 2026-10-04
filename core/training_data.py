"""Project-authored rehearsal examples and separate regression targets.

Raw internet posts, chats and secrets are deliberately not training targets.
"""
SEEDS = [
    ('Scrivi add(a, b) che somma due numeri.', 'def add(a, b):\n    return a + b'),
    ('Scrivi square(x) che calcola il quadrato.', 'def square(x):\n    return x * x'),
    ('Scrivi is_even(n), True se il numero è pari.', 'def is_even(n):\n    return n % 2 == 0'),
    ('Scrivi reverse_text(text) senza modificare maiuscole.', 'def reverse_text(text):\n    return text[::-1]'),
    ('Scrivi clamp(x, low, high), limita x tra low e high.', 'def clamp(x, low, high):\n    return max(low, min(high, x))'),
    ('Scrivi average(values); lista vuota restituisce None.', 'def average(values):\n    return sum(values) / len(values) if values else None'),
    ('Scrivi unique(values), mantiene ordine e rimuove duplicati.', 'def unique(values):\n    return list(dict.fromkeys(values))'),
    ('Scrivi first_or_none(values), primo elemento oppure None.', 'def first_or_none(values):\n    return values[0] if values else None'),
    ('Scrivi initials(name), iniziali maiuscole delle parole.', 'def initials(name):\n    return "".join(word[0].upper() for word in name.split())'),
    ('Scrivi join_words(words), unisci con uno spazio.', 'def join_words(words):\n    return " ".join(words)'),
    ('Scrivi count_lines(text), conta le righe con splitlines.', 'def count_lines(text):\n    return len(text.splitlines())'),
    ('Scrivi strip_text(text), rimuovi spazi iniziali e finali.', 'def strip_text(text):\n    return text.strip()'),
]
HOLDOUT = [
    ('Scrivi cube(x), il cubo di un numero.', 'def cube(x):\n    return x ** 3'),
    ('Scrivi is_positive(x), True solo se x è maggiore di zero.', 'def is_positive(x):\n    return x > 0'),
    ('Scrivi last_or_none(values), ultimo elemento oppure None.', 'def last_or_none(values):\n    return values[-1] if values else None'),
    ('Scrivi maximum(values), massimo oppure None per lista vuota.', 'def maximum(values):\n    return max(values) if values else None'),
]


def examples(verified):
    import hashlib
    from .learning import LESSONS
    tasks={lesson['function']:lesson['task'] for lesson in LESSONS}
    rows=[{'prompt':p,'answer':a,'origin':'project-authored','source_id':None} for p,a in SEEDS]
    for entry in verified:
        if entry.get('status')!='verified' or entry['title'] not in tasks or not entry['code'].strip(): continue
        rows.append({'prompt':tasks[entry['title']],'answer':entry['code'],
                     'origin':'sandbox-verified','source_id':entry['id']})
    unique={hashlib.sha256((r['prompt']+'\n'+r['answer']).encode()).hexdigest():r for r in rows}
    return list(unique.values())[-48:]
