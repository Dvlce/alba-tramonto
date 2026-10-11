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

CODE_SYSTEM = 'Sei Notte. Scrivi soltanto una funzione Python corretta. Conserva esattamente il nome e la firma richiesti. Non ridefinire funzioni builtin.'
LANGUAGE_SYSTEM = 'Sei Notte, assistente locale. Rispondi in italiano con precisione e chiarezza. Non inventare fatti. Usa soltanto i dati pertinenti.'

# Project-authored examples: no private chats or model-generated answers.
LANGUAGE_SEEDS = [
    ('Presentati brevemente.', 'Sono Notte, un assistente locale. Posso aiutarti con spiegazioni, italiano e programmazione.'),
    ('Non conosci la risposta: cosa fai?', 'Dico chiaramente che non ho informazioni sufficienti. Posso cercare una fonte e distinguere i fatti dalle ipotesi.'),
    ('Spiega la differenza tra memoria e addestramento.', 'La memoria conserva documenti che posso consultare. L’addestramento modifica alcuni pesi del modello usando esempi e verifiche.'),
    ('Scrivi una frase italiana con un verbo al passato.', 'Ieri ho scritto una pagina del quaderno.'),
    ('Correggi: io a mangiato una mela.', 'Io ho mangiato una mela.'),
    ('Correggi: qual’è la soluzione?', 'Qual è la soluzione?'),
    ('Spiega quando usare è ed e.', 'È è una forma del verbo essere: il cielo è blu. E collega parole o frasi: pane e acqua.'),
    ('Spiega ha e a con un esempio.', 'Ha è una forma del verbo avere: lei ha un libro. A è una preposizione: vado a casa.'),
    ('Come rendi una spiegazione più chiara?', 'Parto dal punto principale, uso frasi brevi e aggiungo un esempio concreto.'),
    ('Riassumi: Marco legge un libro, poi prepara la cena.', 'Marco legge e poi cucina.'),
    ('Come chiedi un chiarimento?', 'Indico il dettaglio che manca e faccio una domanda precisa, senza inventare una risposta.'),
    ('Un utente ti corregge: come rispondi?', 'Verifico la correzione, riconosco l’errore se presente e aggiorno la risposta.'),
    ('Cos’è una lista in Python?', 'Una lista è una sequenza ordinata e modificabile. Per esempio: numeri = [1, 2, 3].'),
    ('Cos’è un dizionario Python?', 'Un dizionario associa chiavi a valori. Per esempio: persona = {"nome": "Ada", "eta": 30}.'),
    ('Spiega un ciclo for in Python.', 'Un ciclo for visita gli elementi di un iterabile. Esempio: for nome in nomi: print(nome).'),
    ('Perché usare with open in Python?', 'Il blocco with chiude il file anche se si verifica un errore. Si può leggere con with open("note.txt", encoding="utf-8") as file.'),
    ('Spiega async e await in Python.', 'async definisce una coroutine; await attende un’operazione asincrona senza bloccare il ciclo degli eventi, se l’operazione cede il controllo.'),
    ('Spiega una funzione Python.', 'Una funzione raggruppa istruzioni riutilizzabili. Si definisce con def, riceve parametri e può restituire un valore con return.'),
    ('Qual è il compito di HTML?', 'HTML descrive la struttura e il significato dei contenuti di una pagina web, come titoli, paragrafi, collegamenti e moduli.'),
    ('Qual è il compito di CSS?', 'CSS controlla l’aspetto di una pagina: colori, caratteri, spaziatura e disposizione degli elementi.'),
    ('Qual è il compito di JavaScript nel browser?', 'JavaScript gestisce interazioni e aggiornamenti della pagina, per esempio un pulsante che salva un modulo.'),
    ('Spiega Flexbox.', 'Flexbox dispone elementi lungo un asse e gestisce allineamento e spazio. Si abilita con display: flex.'),
    ('Cos’è il responsive design?', 'Un’interfaccia responsive adatta contenuti e controlli allo spazio disponibile, mantenendoli leggibili e utilizzabili sul telefono.'),
    ('Perché aggiungere label a un input?', 'La label descrive il campo e lo rende più accessibile. Il suo attributo for deve corrispondere all’id dell’input.'),
    ('Come rendi accessibile un grafico?', 'Aggiungo titolo, etichette e valori leggibili; fornisco anche una tabella dei dati e non distinguo le serie solo tramite il colore.'),
    ('Spiega GET e POST in HTTP.', 'GET richiede una rappresentazione di una risorsa. POST invia dati da elaborare al server, per esempio il contenuto di un modulo.'),
    ('Cos’è JSON?', 'JSON è un formato testuale per scambiare dati: oggetti, array, stringhe, numeri, booleani e null.'),
    ('Perché verificare response.ok con fetch?', 'fetch può risolvere la promessa anche per un errore HTTP. response.ok indica uno stato tra 200 e 299.'),
    ('Cos’è Git?', 'Git è un sistema di controllo versione distribuito. Conserva la storia delle modifiche e permette di lavorare con rami e commit.'),
    ('Che differenza c’è tra Git e GitHub?', 'Git gestisce il controllo versione; GitHub ospita repository e strumenti di collaborazione, come issue e pull request.'),
    ('Come valuti se un modello migliora?', 'Confronto vecchia e nuova versione sugli stessi test indipendenti. Misuro correttezza, loss di validazione, tempi e velocità; il risultato può anche peggiorare.'),
    ('Il 100% di indicizzazione significa conoscere tutta Wikipedia?', 'No. Significa che tutti i documenti importati sono ricercabili. Non misura quanta parte di Wikipedia conosco o la qualità delle mie risposte.'),
]

# Separate prompts and targets, never inserted into the training dataset.
LANGUAGE_HOLDOUT = [
    {'prompt': 'A cosa serve HTML in una pagina?', 'answer': 'HTML definisce la struttura dei contenuti di una pagina web.', 'keywords': [['struttura', 'contenut']]},
    {'prompt': 'Quale tecnologia regola colori e caratteri di un sito?', 'answer': 'CSS regola colori, caratteri e aspetto di un sito.', 'keywords': [['css']]},
    {'prompt': 'Che cosa rappresenta un dizionario nel linguaggio Python?', 'answer': 'Un dizionario Python associa chiavi a valori.', 'keywords': [['chiav'], ['valor']]},
    {'prompt': 'Che cosa fa il comando git commit?', 'answer': 'git commit registra una versione delle modifiche nel repository locale.', 'keywords': [['modific', 'version', 'istantanea', 'snapshot']]},
    {'prompt': 'Che differenza c’è fra ricordare un documento e modificare i pesi di una rete?', 'answer': 'Ricordare un documento permette di consultarlo; addestrare la rete modifica i pesi tramite esempi.', 'keywords': [['document', 'memori'], ['pes', 'addestr']]},
    {'prompt': 'Riscrivi correttamente: Luca a un quaderno.', 'answer': 'Luca ha un quaderno.', 'keywords': [['luca ha un quaderno']]},
]


def curriculum(verified, taught=()):
    import hashlib
    rows = [{**r, 'task': 'code', 'system': CODE_SYSTEM} for r in examples(verified)]
    rows += [{'prompt': p, 'answer': a, 'task': 'language', 'system': LANGUAGE_SYSTEM,
              'origin': 'project-authored', 'source_id': None} for p, a in LANGUAGE_SEEDS]
    rows += [{'system': LANGUAGE_SYSTEM, **r} for r in taught]
    unique = {hashlib.sha256((r['prompt']+'\n'+r['answer']).encode()).hexdigest(): r for r in rows}
    return list(unique.values())[:128]


def validation():
    return ([{'prompt': p, 'answer': a, 'task': 'code', 'system': CODE_SYSTEM} for p, a in HOLDOUT]+
            [{**r, 'task': 'language', 'system': LANGUAGE_SYSTEM} for r in LANGUAGE_HOLDOUT])


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
