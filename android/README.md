# Alba · Albi per Android

APK piccolo, senza modello AI o credenziali incorporati. Apre Alba e Tramonto nel browser tramite una Custom Tab compatibile: le sessioni e i provider OAuth restano gestiti dal browser. Richiede Android 6+ e un server HTTPS raggiungibile; l’AI continua a essere eseguita sul server. Non è un’app offline e non richiede Tailscale sul telefono. “Cambia server HTTPS” permette di scegliere la propria installazione.

Installa l’APK scaricato dal sito o da GitHub Releases consentendo l’installazione dalla sorgente scelta. Il pacchetto è firmato con una chiave di release privata: le versioni successive della stessa distribuzione devono usare la stessa chiave. Firma e manifest sono verificati nella build; il funzionamento su un telefono va verificato sul proprio dispositivo.

Build senza Android Studio/Gradle: Python 3, JDK 17 e Android SDK con `platforms;android-36`, `build-tools;36.0.0`. Scarica gli strumenti dal [sito ufficiale Android](https://developer.android.com/studio), verifica il checksum pubblicato e installa i due pacchetti con il gestore SDK. Poi:

```sh
python3 android/build.py --sdk /percorso/android-sdk --server https://alba.example.org
```

Il risultato è `dist/alba-albi.apk`. La chiave di firma viene creata in `~/.local/alba-signing` con permessi protetti; non viene pubblicata nel repository. `--signing-dir` seleziona un altro archivio privato. Conserva chiave e password per gli aggiornamenti. Nessun account Play Store è configurato.
