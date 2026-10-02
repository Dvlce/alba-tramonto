# Alba · Tramonto per Android

La versione 1.1.0 apre Alba e Tramonto **dentro l’app**, con una WebView: non avvia una Custom Tab o il browser per usare la piattaforma. I pulsanti Alba/Tramonto, il tasto Indietro, il caricamento immagini, la stampa A4/PDF e il salvataggio di JSON/SVG usano la navigazione e i selettori Android. Le dimensioni e l’allineamento degli oggetti sono gli stessi del sito. Rotazione e apertura del selettore immagini conservano la pagina corrente.

Richiede Android 6+ con Android System WebView aggiornato e un server HTTPS raggiungibile. **Non è offline**: AI, account e quaderni rimangono sul server. Non contiene modello, password o dati personali. Il menu ⋯ permette di cambiare server. Solo i collegamenti esterni selezionati esplicitamente (per esempio Telegram o un’informativa esterna) vengono aperti nella rispettiva app.

Al primo avvio accedi con password o chiave personale; la sessione è conservata nell’app, separatamente dal browser. L’accesso SMS funziona se configurato sul server. Google/GitHub/Discord richiedono il browser secondo le regole dei provider e non sono integrati in questo client: usa uno degli altri metodi. HTTPS è obbligatorio; certificati non validi non vengono accettati. I file esportati possono essere salvati tramite il selettore documenti, fino a 32 MB, senza permessi generali sulla memoria del telefono.

Installa l’APK dal sito o dal file di release consentendo l’installazione dalla sorgente scelta. La versione 1.1.0 mantiene `local.alba` e usa la chiave di firma della distribuzione precedente, quindi può aggiornarla senza disinstallare. Le versioni successive devono conservare la stessa chiave.

## Build

Python 3.9+, JDK 17 e Android SDK con `platforms;android-36` e `build-tools;36.0.0`. Installa gli strumenti dal [sito ufficiale Android](https://developer.android.com/studio), poi:

```sh
python3 android/build.py --sdk /percorso/android-sdk --server https://alba.example.org
```

Sul Mac con il JDK Homebrew:

```sh
JAVA_HOME=/opt/homebrew/opt/openjdk@17 PATH=/opt/homebrew/opt/openjdk@17/bin:$PATH \
  python3 android/build.py --server https://alba.example.org
```

Il risultato è `dist/alba-albi.apk`. La build genera le risorse del server nella directory di build senza modificare quelle tracciate nel repository; pulisce i vecchi `.class`, verifica la firma e stampa lo SHA256. La chiave privata resta in `~/.local/alba-signing` con permessi protetti; `--signing-dir` seleziona un altro archivio. Conserva chiave e password per gli aggiornamenti.

Verifica sul dispositivo: primo login, Alba → Tramonto, scelta di un’immagine, rotazione durante la scrittura, formula/grafico/circuito inseriti e ridimensionati, esportazione JSON/SVG, PDF A4, tasto Indietro con salvataggio, server non raggiungibile e ritorno della connessione. La sola build non equivale a questa verifica su telefono.
