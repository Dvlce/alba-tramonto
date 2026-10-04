# Alba · Tramonto · Notte — Native Android 1.3

The Android app uses Java and Android Views. It contains **no WebView, Javascript engine or browser UI**. Chat is the main screen; a dropdown contains Alba, Tramonto notebooks, memory, topic diary, all activity, personal-model training, token statistics, emotions, hardware and settings.

Italian and English UI follow the phone language, with a manual choice in Settings. AI responses follow the language of the message. The AI, SQLite database, notebooks and training run on the Raspberry; the APK is a native network client, not an on-phone LLM. HTTPS is required.

Login uses your existing account or a one-time `/web_key` Telegram link. Sessions and recovered page drafts are encrypted with an Android Keystore key, excluded from backups. Passwords and one-time keys are not stored. API mutations use CSRF and same-origin requests; redirects and invalid TLS certificates are rejected. HTTP 401 / expired sessions return to native login.

Tramonto has native text editing, ink, JSON export and optimistic version checks. Saving preserves existing graph, formula, circuit, network and image data. Its complete visual math/electronics/network laboratories remain in the existing web portal; native editing of those advanced objects, image upload and PDF printing are not part of this release. The native APK does not open that portal inside itself.

The package `local.alba`, signing certificate and HTTPS App Links remain unchanged. Update the APK without uninstalling. The first native login is required because the old browser session cannot be reused by the native API client. Phone-specific Telegram in-app browser settings may still affect external app opening.

## Build

Python 3.9+, JDK 17, Android SDK 36 and build-tools 36.0.0:

```sh
python3 android/build.py --sdk /path/to/android-sdk --server https://alba.example.org
```

Output: `dist/alba-albi.apk`, `dist/assetlinks.json`. The private signing key stays in `~/.local/alba-signing`; keep it for future updates. Publish the generated assetlinks at `/.well-known/assetlinks.json` on the same HTTPS origin. The manifest host is generated from `--server`.

## Native UI verification

```sh
python3 android/test_native.py --sdk /path/to/android-sdk
adb install -r dist/alba-albi.apk
adb install -r android/build/smoke/native-smoke.apk
adb shell am instrument -w local.alba.smoke/local.alba.NativeUiSmoke
```

The test APK is separate from the release. Its explicit fixture transport checks native markdown/table rendering, menu navigation, retained chat drafts, diary, training/system/activity screens, Italian/English UI, notebook content preservation and versioned saving. It never uses real credentials, trains models or sends Telegram messages. Production API tests verify authentication, authorization and CSRF independently. GitHub Actions runs the emulator on the CI runner, not on the user's Mac. Test signing keys created in CI are ephemeral; published APKs use the existing release key.
