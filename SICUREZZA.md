# Sicurezza della piattaforma

Il sito ascolta solo su `127.0.0.1:8088`, Ollama su loopback. L’accesso pubblico richiede un reverse proxy HTTPS (nell’installazione corrente: Tailscale Funnel). Gli utenti del sito non devono installare Tailscale.

Sul Raspberry il firewall `alba-firewall.service` applica la tabella separata `inet alba_guard`, preservando le regole gestite da Tailscale. SSH è consentito solo tramite Tailscale e solo con chiavi, senza root o password. Fail2ban limita i tentativi; gli aggiornamenti di sicurezza Debian sono automatici, senza riavvio automatico. Avahi è disabilitato. `deploy/harden_pi.py` verifica prima che esista una chiave autorizzata: leggere e adattare lo script prima di usarlo su un’altra macchina.

Esempio di accesso dopo la configurazione di una chiave:

```sh
ssh -i ~/.ssh/alba_pi_ed25519 UTENTE@INDIRIZZO_TAILSCALE
```

La chiave privata resta nel Mac, con permessi 0600. Non pubblicarla. La password macchina continua a servire per sudo/console, non per SSH. Conserva una copia sicura della chiave e i backup di ripristino.

Alba viene eseguita con un utente di sistema dedicato e un servizio con filesystem protetto. I dati e i backup sono accessibili solo al servizio/root. Le richieste JSON, la concorrenza, i tentativi di login e la memoria dei limitatori hanno limiti. Cookie Secure/HttpOnly, verifiche CSRF e Origin, CSP e intestazioni di sicurezza proteggono gli accessi web. Il proxy non deve pubblicare direttamente database, `.env`, log o directory dei backup.

Le simulazioni ngspice accettano solo componenti e parametri strutturati. Il server genera la netlist: nessun testo SPICE arbitrario, comando shell o include fornito dall’utente. Bubblewrap esegue il worker in filesystem e rete isolati, senza cartella home, database o variabili segrete; limita CPU, RAM, dimensione dei risultati e durata. Solo gli amministratori possono accedere al laboratorio; i lavori e i quaderni restano separati per proprietario.

Le memorie personali non entrano nei gruppi. Le esportazioni richiedono una chiave monouso del proprietario; l’amministratore non ottiene le password. OAuth e SMS aggiungono identità verificate senza fusione automatica per email. La cancellazione rimuove anche feedback, collegamenti esterni e posizione di lettura; un restore invalida sessioni e verifiche pendenti.

I backup sono cifrati; il database live è protetto dai permessi del sistema, non cifrato integralmente su disco. Conserva separatamente le chiavi `data/auth.key` e la chiave di cifratura backup per un ripristino su un’altra macchina. La sicurezza richiede anche aggiornamenti, controllo dell’account amministratore e protezione fisica del Raspberry.

Il servizio ammette AF_NETLINK per preparare il loopback del namespace privato di bubblewrap. Il simulatore rimane senza rete esterna e senza accesso a dati/chiavi. `LimitAS=1G` limita lo spazio di indirizzi dei processi dell’applicazione; il worker ha inoltre un limite proprio di 384 MiB. `MemoryMax=512M` richiede il controller memory di cgroup, assente sul kernel del Raspberry di riferimento: non rappresenta su quel sistema un limite di RAM effettivamente applicato.

`RestrictSUIDSGID` è disattivato perché il filtro di systemd blocca openat2, necessario a bubblewrap 0.12. Restano attivi NoNewPrivileges, capability vuote, filesystem del servizio in sola lettura e utente dedicato senza login. Il worker vede una directory /proc vuota: non può usare /proc per raggiungere dati o processi del servizio.
