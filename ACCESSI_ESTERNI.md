# Accessi esterni: configurazione dell’amministratore

L’integrazione è inclusa, ma i provider restano disattivati finché il gestore non registra le applicazioni. Apri **Gestione bot → Accessi e registrazione**. ID pubblici e segreti vengono inviati con HTTPS; i segreti sono cifrati nel database con la chiave locale `data/auth.key`. Non vengono restituiti al browser né scritti nell’audit. Il campo segreto vuoto mantiene quello salvato. Deseleziona “Attiva” per disabilitare un provider.

Usa l’URL callback mostrato dal pannello, senza modificarlo. In questa installazione la base pubblica è quella del sito: la configurazione di altre installazioni usa `PUBLIC_URL` in `.env`.

## Google / Gmail

1. Crea un progetto nel [Google Cloud Console](https://console.cloud.google.com/).
2. Configura Google Auth Platform: nome dell’app, destinatari, contatto, informativa privacy e domini autorizzati. Durante i test inserisci gli utenti di prova.
3. Crea un client OAuth di tipo **Applicazione web**. Aggiungi l’URL callback `/auth/google/callback` del tuo sito agli URI di reindirizzamento autorizzati.
4. Copia Client ID e Client secret nel pannello e attiva Google.

Gli scope sono `openid email profile`: Alba non legge la posta Gmail. L’identità viene verificata dal provider; l’email deve risultare verificata. Il flusso usa state e PKCE S256. [Documentazione Google OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect).

## GitHub

1. In GitHub: Settings → Developer settings → OAuth Apps → New OAuth App.
2. Homepage: URL del tuo sito. Authorization callback URL: `/auth/github/callback` del tuo sito.
3. Genera il Client secret; inserisci ID e segreto nel pannello, poi attiva.

Gli scope sono `read:user user:email`. Alba seleziona un’email verificata; l’identificativo GitHub è la chiave dell’associazione. Non richiede accesso alle repository. [Creare una OAuth App](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/creating-an-oauth-app).

## Discord

1. Nel [Developer Portal](https://discord.com/developers/applications), crea un’applicazione.
2. OAuth2 → Redirects: aggiungi `/auth/discord/callback` del tuo sito.
3. Copia Client ID e Client secret nel pannello e attiva.

Gli scope sono `identify email`. Alba richiede che Discord segnali l’email come verificata. Non legge chat Discord e non richiede un bot Discord. [Documentazione OAuth2](https://docs.discord.com/developers/topics/oauth2).

## Numero di telefono / Twilio Verify

1. Crea un account Twilio e un servizio **Verify** con canale SMS.
2. Inserisci Account SID (`AC…`), Auth token e Verify Service SID (`VA…`) nel pannello.
3. Configura nel portale Twilio i paesi consentiti, i limiti di spesa e la protezione antiabuso; poi attiva il provider.

Alba permette al massimo 3 invii per numero al giorno, 20 invii totali al giorno e un invio al minuto per numero. La verifica scade dopo 10 minuti e ammette 5 tentativi. I limiti sono conservati localmente anche dopo un riavvio. Twilio può applicare costi; gli account di prova hanno restrizioni sui destinatari. [Verify API](https://www.twilio.com/docs/verify/api).

Il numero viene trasmesso a Twilio per la verifica. Alba conserva temporaneamente il numero cifrato nel flusso; l’identità persistente usa un’impronta protetta, con le ultime quattro cifre nel nome visualizzato. Il codice SMS non viene conservato.

## Collegare l’identità Telegram

Per mantenere la chat unificata e le memorie: entra prima con `/web_key` o `/web_password` di Telegram, apri **Dispositivi → Account collegati**, scegli “Collega Google/GitHub/Discord” e completa la verifica. Gli accessi successivi con quel provider usano lo stesso utente Telegram.

Un accesso esterno effettuato prima del collegamento crea invece un account web autonomo. Due account non vengono uniti perché hanno la stessa email. Un’identità già associata a un altro utente non può essere sottratta. La registrazione rispetta il limite di 20 utenti autorizzati; il pannello può autorizzare gli account in attesa. La revoca amministrativa impedisce la riattivazione automatica.

Per provare: attiva un provider, apri una finestra privata, seleziona privacy/regole e accedi. Verifica nome, persistenza del profilo e isolamento. Disattiva il provider per tornare agli accessi Telegram/password.
