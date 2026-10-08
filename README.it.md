# Alba + Tramonto + Notte

[Progetto di ottimizzazione](docs/TEST_LAB.md): sito IT/EN con informazioni, news, benchmark e storia su `/optimization`. La **Test Lab** di Notte e Android nativo 1.4 confronta lo stesso modello tramite Ollama normale e SSD, con risposte, istogrammi e report esportabili. [Risultati e limiti misurati](docs/TEST_LAB_RESULTS.md).

AI conversazionale locale, Telegram e web, con memoria nel tempo. **Notte / ALBA-CORE** aggiunge una personalità autonoma con emozioni persistenti, memoria vettoriale locale, riflessione, riassunti, ricerca Wikipedia e messaggi Telegram a Matt. [Architettura, configurazione e limiti di ALBA-CORE](docs/ALBA_CORE.md). Tramonto è il quaderno riservato all’amministratore: pagine A4, immagini nel testo, matematica, disegno, circuiti ngspice e reti didattiche.

Menu Alba / Tramonto / Notte uniforme nei tre siti, con icone esistenti, spazio attivo, navigazione da tastiera e supporto mobile. Animazioni brevi d’ingresso e transizione coerenti con tema e palette; rispettano il movimento ridotto. Tramonto salva gli appunti prima del cambio di spazio e mantiene aperto l’editor se il salvataggio fallisce.

![Tramonto](docs/tramonto.png)

- Memorie private e di gruppo separate; fatti dichiarati, inferenze e informazioni incerte con fonti e stato. SQLite FTS5, contesto limitato, profili persistenti e feedback per utente. Non effettua fine-tuning dei pesi del modello.
- Telegram privato/gruppi: menzioni, reply, comandi e modalità automatica configurabile. Sito con lo stesso archivio Telegram dopo un’associazione verificata.
- Chiavi web monouso e password personali, browser ricordati e revocabili. Accessi opzionali Google/GitHub/Discord/Twilio Verify configurabili con segreti cifrati. Nessuna fusione automatica per email.
- 20 utenti autorizzati, 5 persone attive, coda, Stop, limiti mensili di token, calendario di utilizzo, CPU/RAM/disco ogni 2 secondi, audit e backup cifrati con retention.
- Tema chiaro/scuro, classico/neomorfismo/vetro, logo animato e Albi, mascotte albicocca originale.
- Tramonto: raccolta quaderni, otto stili di carta, dodici font (otto aggiuntivi inclusi localmente), tabelle e modelli. Pagine A4 numerate, continuazione del testo lungo e ripristino della pagina/posizione. Immagini incollate/caricate, trascinabili e ridimensionabili, con testo a fianco. Palette di componenti con simboli, ricerca e categorie; fili automatici dai terminali, svolte a 90°, anteprima, colori e nodi di derivazione. Esempi di oscillatori Wien, RC e Colpitts; pennelli, forme, frecce e armoniche di Fourier. Nel testo: simboli matematici e greci, unità, scorciatoie (`<=`, `>=`, `~=`, `\omega` + spazio), apici/pedici annidati. Formule modificabili con editor matematico visivo e sorgente LaTeX conservata nel foglio; parentesi regolabili e sistemi con righe aggiuntive. Testi nel disegno modificabili e trascinabili; ⌘Z / Ctrl+Z per annullare disegni, schemi e reti. Laboratorio del font personale: gruppi di maiuscole, minuscole, numeri, accenti, greco e simboli matematici; disegno separato dei caratteri, salvataggio nella pagina, uso nel testo e nel disegno, esportazione OTF; caratteri mancanti con font di riserva. Raccolta di formule disegnate con nome, inseribili nel quaderno o nel disegno. Allineamento del testo a sinistra, centrato, a destra e giustificato, conservato al salvataggio. Grafici da testo e LaTeX (anche con colorbox), assi adattabili, dominio, zeri, studio del segno, quadranti occupati, tabella valori, derivata e aree evidenziate. Studio e grafico inseribili nel quaderno; i risultati campionati sono indicati come stime numeriche. Grafici e laboratori inseribili nella pagina come immagini PNG, con selezione, maniglia di ridimensionamento, larghezza, allineamento e spostamento nel testo. Comandi raggruppati, impostazioni dell’oggetto accanto al foglio e stampa della sola pagina A4.
- Aspetto di Alba e Tramonto: Classico, Neomorfismo, Vetro, Claymorphism, Cybercore, Neobrutalism, Scrapbook e Surrealism. Luminosità chiara/scura/grigia/nera e sei palette indipendenti, conservate sul dispositivo. Menu Aspetto su Alba, anche prima del login; stampa A4 di Tramonto bianca senza decorazioni. Icone Lucide locali con licenza inclusa.
- Matematica: LaTeX/KaTeX, tre curve, funzioni trigonometriche/iperboliche, limiti numerici, derivate simboliche, integrali e zeri numerici. Le stime numeriche non sostituiscono dimostrazioni.
- Elettronica: 35 componenti e strumenti, generatore di funzioni, sommatore ideale Σ con guadagni A/B e riferimento, fili, rotazione/undo; ngspice locale isolato per DC, transitorio, sweep AC e DC, CSV/netlist. Oscilloscopio differenziale con morsetti A+/A− e B+/B−, acquisizione animata, riproduzione con avanzamento/arretramento per campione, zoom temporale e scale/offset indipendenti. Due cursori sui campioni originali mostrano tempo, tensioni e differenze; il CSV conserva tutti i campioni. Finestra dello strumento ridimensionabile anche a schermo intero, con aspetto classico ispirato ai riferimenti XSC1: pannello grigio, schermo chiaro con griglia, tracce nero/blu, comandi separati per base tempi e canali A/B, misure T1/T2 sotto il grafico. Il simbolo nello schema mostra due tracce e i nuovi strumenti hanno i quattro morsetti in basso. Area schemi espandibile fino a 50.000 × 50.000 unità con zoom, panoramica e pulsante «Centra progetto» che recupera lo schema anche da una vista lontana; il rendering esclude gli oggetti fuori vista e riutilizza i percorsi dei cavi. Le svolte dei fili seguono gli spostamenti dei gruppi e il tratto vicino al morsetto si adatta quando si muove un solo componente, conservando nodi, terminali e colori. Modelli generici didattici, con macromodello TL081 fisso di Texas Instruments selezionabile nelle proprietà. «Schema dell’immagine · TL081» ricrea i tre generatori (2 Vpk/1500 Hz, 5 Vpk/10000 Hz, 0,5 Vpk/670 Hz, fase 0°), il sommatore a tre ingressi A1, U1/U2 a ±15 V, D1, C1 da 10 nF e S1 azionabile con A; il canale A misura la somma e B l’uscita. La retroazione di U1 precede D1 come nel riferimento. «Filtro RC · immagine (100 Hz)» riproduce il secondo riferimento: generatore sinusoidale da 100 mVpk/100 Hz/0°, R1 da 15 kΩ, C1 da 100 nF e oscilloscopio A sull’ingresso, B sul condensatore, entrambi riferiti alla massa; durata 50 ms, 5000 campioni richiesti. Il modello del diodo è generico perché la foto non ne specifica il codice. Il macromodello TL081 è quello pubblicato da [Texas Instruments (SLOJ069)](https://www.ti.com/lit/zip/sloj069); non è una replica di Multisim.
- Simboli, componenti, pennelli, formule e proprietà in pannelli a destra con scorrimento indipendente. Sui dispositivi piccoli si aprono dal pulsante strumenti senza spostare il foglio.
- Schemi in vista tecnica: griglia fine su fondo bianco, simboli sottili, nomi e valori su righe separate, numerazione dei pin degli operazionali e colori rapidi dei fili. L’aspetto morbido Tramonto si può selezionare nello stesso pannello. Esempio di rivelatore di picco con due operazionali generici a ±15 V, diodo, condensatore, scarica con S1 e oscilloscopio ingresso/uscita, verificato in ngspice.
- Reti: nove dispositivi, cavi, VLAN, gateway e interfacce; ping animato e traceroute didattici, controllo IP/gateway/collegamenti, duplicazione e disposizione a griglia. CIDR con intervallo host/wildcard, suddivisione uniforme e VLSM, rapporti e tabelle inseribili nel quaderno. Selezione multipla con Maiusc/clic, pressione prolungata o area, spostamento del gruppo, Canc/Delete e Annulla nei circuiti e nelle topologie. Console show/diagnose/traceroute. Non esegue Cisco IOS né invia pacchetti reali; il routing tra più router non è implementato.

## Installazione Linux / Raspberry Pi

Requisiti consigliati: Raspberry Pi 5, 8 GB, Linux 64 bit, almeno 10 GB liberi per modelli e dati. Il setup analizza RAM/CPU/disco e sceglie il modello iniziale. I 750 GB non sono necessari: la retention si configura in `.env`.

```sh
git clone https://github.com/Dvlce/alba-tramonto.git
cd alba-tramonto
python3 install.py
```

Il setup installa dipendenze Linux, ambiente Python, Ollama se assente, modello e servizio. Chiede in modo protetto il token BotFather e l’ID admin; puoi omettere Telegram e creare un amministratore locale da terminale. Conserva una `.env` esistente. I download richiedono internet durante il setup; le risposte del modello girano localmente. `--skip-system`, `--no-model`, `--no-service` permettono installazioni personalizzate.

Credenziali iniziali in `data/first-access.txt`, permessi 0600: leggile dal terminale, conservale e rimuovi il file. Il server ascolta **solo su 127.0.0.1:8088**. Pubblicalo con un reverse proxy HTTPS; configura `PUBLIC_URL` e riavvia. Tailscale Funnel è una possibilità: gli utenti del sito e Telegram non devono installare Tailscale. Non pubblicare la porta Ollama o il database.

Il servizio generato dal setup gira come l’utente installatore. Per un’installazione più protetta usa un utente di servizio dedicato e adatta `deploy/alba.service`; [SICUREZZA.md](SICUREZZA.md) descrive le misure applicate sull’installazione di riferimento. `deploy/harden_pi.py` è specifico di quella macchina: leggerlo e adattare utenti/chiavi prima di usarlo altrove. Non cambia SSH/firewall automaticamente durante il setup generale.

Backend e modello sono sostituibili:

```ini
MODEL=qwen3:4b-instruct-2507-q4_K_M
LLM_BACKEND=ollama
LLM_URL=http://127.0.0.1:11434
MAX_USERS=20
MAX_ONLINE=5
```

Con 8 GB, il modello quantizzato 4B e SQLite sono una scelta leggera; viene eseguita una generazione alla volta. I cinque posti non significano cinque modelli caricati. Con meno RAM il setup propone `qwen3:1.7b`. Per llama.cpp usa `LLM_BACKEND=llamacpp` e il suo endpoint OpenAI-compatible locale. Valuta qualità e latenza sul tuo hardware prima di cambiare modello.

## Telegram, sito e accessi esterni

Crea il bot con BotFather; imposta il token nel setup o in `.env`. Per i gruppi abilita i messaggi necessari nelle impostazioni BotFather e aggiungi il bot. `/start`, `/help`, `/profile`, `/memory`, `/timeline`, `/search`, `/stats`, `/export`, `/export_key`, `/export_personality`, `/export_prompt`, `/forget`, `/backup`, `/web_key`, `/web_password`, `/feedback`, `/memory_key`, `/stop`. Comandi admin separati; le operazioni sono registrate. Per configurare un gruppo l’amministratore Alba deve essere anche amministratore Telegram del gruppo.

`/web_key` in privato genera un pulsante di login personale: la chiave è nel frammento URL, rimossa subito dal browser e consumata una volta. Con accesso automatico attivo si autorizza fino al limite di 20. `/web_password` crea o rinnova le proprie credenziali. Esportazioni solo con verifica privata e chiave monouso; l’admin non recupera password o chiavi originali. I file separano dati originali, riassunti, inferenze e incertezze, senza includere dati privati di gruppi/altri utenti.

L’amministratore può richiedere dal pannello il consenso per consultare le memorie di un utente. La persona genera `/memory_key` nella propria chat privata e consegna volontariamente il codice: monouso e valido 15 minuti, apre una consultazione di 15 minuti per quell’amministratore. `/memory_key revoke` revoca codici e accessi. Il permesso non consente esportazioni; chiavi e dati non vengono registrati nei log.

Google/GitHub/Discord/SMS sono **predisposti, disabilitati senza credenziali**. [Istruzioni complete](ACCESSI_ESTERNI.md). Google usa identità/email/profilo, non legge Gmail. Per mantenere l’identità Telegram, accedi prima con Telegram e collega il provider dalla sezione Dispositivi.

Da terminale, con permessi del gestore:

```sh
.venv/bin/python cli.py users
.venv/bin/python cli.py allow ID_TELEGRAM
.venv/bin/python cli.py web-key ID_TELEGRAM
.venv/bin/python cli.py password ID_TELEGRAM
.venv/bin/python maintenance.py backup
```

Restore: ferma il servizio, poi `maintenance.py restore FILE --service-stopped`; richiede le chiavi locali e invalida gli accessi precedenti. I backup sono cifrati, il database live è protetto dai permessi. `/forget all confermo` cancella anche i backup precedenti dell’installazione; le copie già scaricate e i messaggi Telegram vanno rimossi separatamente.

## Android e integrazione

APK in [Releases](https://github.com/Dvlce/alba-tramonto/releases), oppure `/download/alba-albi.apk` se il gestore lo ha installato sul server. La versione 1.3.0 ha interfaccia Android nativa, senza WebView, chat principale e menu a tendina, in italiano e inglese. Include Android App Links verificati per i link personali Telegram. Invia `/notte` nella chat privata admin di Alba per associare Matt ai messaggi autonomi. L’editor nativo salva testo, disegno e JSON e conserva gli oggetti avanzati; i laboratori completi, le immagini e il PDF A4 restano nel portale web; non incorpora dati personali o un LLM e richiede connessione al server. Il server HTTPS si può cambiare dall’app. [Sorgenti e build Android](android/README.md).

Per integrare il motore in un sistema esistente: [alba-local-kit](https://github.com/Dvlce/alba-local-kit), package Python con adapter, Telegram e chiavi web/CLI.

## Verifica

```sh
.venv/bin/python -m unittest discover -s tests
```

341 scenari/test automatici sul Raspberry e in Linux CI, inclusi quattro circuiti eseguiti realmente in ngspice isolato. I test del simulatore richiedono Linux, ngspice, bubblewrap e namespace utente disponibili. Test browser separati con Playwright: `tests/browser_check.py`, `tests/tramonto_browser_check.py`, `tests/labs_browser_check.py`, `tests/notebook_editor_check.py`, `tests/math_font_browser_check.py`, `tests/function_study_browser_check.py`, `tests/appearance_network_check.py`, `tests/alba_appearance_check.py` (installare Playwright e Chromium nell’ambiente di test). Database temporanei, nessuna chiamata LLM necessaria. Verificano anche privato→gruppo, export altrui negato, immagini, A4, reload, simulazioni, account, CSRF, revoche e backup/restore.

Alba è un supporto alla riflessione e ai problemi quotidiani, non un servizio clinico o di emergenza. I controlli di provenienza riducono gli errori, ma un modello può ancora produrre risposte inesatte. Il gestore configura privacy, contatti, accessi e manutenzione.

MIT per il codice originale. Le librerie in `vendor/` includono le proprie licenze; i modelli hanno licenze separate. Nessuna telemetria applicativa, nessun archivio personale, token o chiave incluso nel repository.

[Misure sul Raspberry: otto modelli, 64 prove e training personale](docs/PI_INFERENCE_RESULTS.md).

### Importazione Multisim in Tramonto

In Schemi, il pannello strumenti a destra offre **Importa Multisim / SPICE**.
Il convertitore legge i contenitori XML compressi Multisim (verificati su due
progetti `.ms14`) e le netlist testuali `.cir`, `.sp`, `.net`. Ricostruisce oggetti
modificabili, valori, masse e connessioni; i tracciati vengono ridisegnati.
Supporto nativo: R/C/L, sorgenti AC sinusoidali e DC, massa, strumenti di misura,
oscilloscopio A/B, TL081 con piedinatura riconosciuta, diodi e SPST riconosciuti.
La netlist supporta R/C/L, sorgenti DC/SIN, diodi, NPN/PNP generici e TL081.
L'anteprima elenca le differenze dei modelli prima dell'applicazione annullabile.
Componenti sconosciuti, trigger esterni collegati e circuiti gerarchici interrompono
la conversione senza modificare la pagina. Non sono importati risultati di
simulazione o modelli eseguibili. Limiti: file 8 MB, XML decompresso 12 MB,
100 oggetti e 200 collegamenti. Decoder DCL Python adattato da blast di Mark Adler
(licenza e attribuzione nel sorgente).

Per inserire un interruttore in serie: scegli la sua icona e tocca un tratto libero
del cavo. Doppio clic apre/chiude l'interruttore; il tasto assegnato nelle proprietà
fa lo stesso. **Simula** acquisisce lo stato aggiornato. I quattro morsetti
dell'oscilloscopio sono sotto il simbolo, anche negli schemi precedenti.
