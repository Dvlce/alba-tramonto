# Alba + Tramonto + Notte

[Italian documentation](README.it.md)

Local conversational AI for Telegram and the web, with persistent memory. **Alba** provides conversation and account management. **Tramonto** is an administrator-only notebook with A4 pages, inline images, mathematics, drawing, isolated ngspice circuits, and educational network tools. **Notte / ALBA-CORE** adds an autonomous personality with persistent emotions, local vector memory, reflection, summaries, Wikipedia research, and Telegram messages to its paired administrator.

All three web spaces share the same dropdown navigation: existing brand icons, consistent labels and sizing, a current-space indicator, keyboard navigation, and mobile support. Short entrance and navigation animations follow the selected theme and palette. Tramonto uses abstract warm horizon light with its existing ◒ mark, Alba uses its intertwined symbol, and Notte uses its crescent. Reduced motion and the animation preference are respected. Leaving Tramonto waits for notebook changes to save; a failed save keeps the editor open.

[Optimization project](docs/TEST_LAB.md): the IT/EN site at `/optimization` publishes information, sourced news, benchmarks and evolution history. Notte and native Android 1.4 include a private **Test Lab** comparing the same model and prompt through normal Ollama and SSD, with actual outputs, charts and exported reports. [Measured comparison and limitations](docs/TEST_LAB_RESULTS.md).

[ALBA SSD Runtime](docs/SSD_RUNTIME.md): esecuzione del GGUF scelto, kernel ARM nativi, mmap senza copie complete per i modelli grandi, confronto del decoding speculativo e controllo RAM/temperatura. Integrato nella chat avanzata di Notte, con identità del modello e benchmark verificabili. Non promette inferenza fluida oltre la RAM né implementa la cache esperti universale di Colibri.

![Tramonto](docs/tramonto.png)

## Features

- Separate private and group memories, with sources and status for declared facts, inferences, and uncertain information. SQLite FTS5, bounded context, persistent profiles, and per-user feedback. Alba's conversational memory does not fine-tune model weights.
- Private and group Telegram conversations: mentions, replies, commands, and configurable automatic replies. The web interface uses the same Telegram archive after verified account linking.
- Single-use web keys, personal passwords, and remembered browsers that users can revoke. Optional Google, GitHub, Discord, and Twilio Verify sign-in, with encrypted provider secrets. Accounts are not automatically merged by email.
- Up to 20 authorized users and 5 active chat slots, a queue, Stop controls, monthly token limits, a usage calendar, CPU/RAM/disk readings every 2 seconds, auditing, and encrypted backups with retention.
- An animated Alba logo and Albi, the original apricot mascot.
- Tramonto notebook collections, eight paper styles, four fonts, tables, and templates. Numbered A4 pages, continuation of long text, and restoration of the current page and position. Pasted or uploaded images can be moved and resized with text alongside them. Formulas, graphs, and lab results can be inserted as PNG notebook objects, with selection, resize handles, width, alignment, and movement controls. Grouped editing commands, an object inspector beside the page, and printing of the A4 page alone.
- Alba and Tramonto appearance settings: Classic, Neomorphism, Glass, Claymorphism, Cybercore, Neobrutalism, Scrapbook, and Surrealism. Light, dark, gray, and black modes, plus six independent palettes remembered on the device. Alba's appearance menu is available before login. Tramonto prints clean white A4 pages without decorative effects. Lucide icons are served locally with their license included.
- Mathematics: LaTeX/KaTeX, three plotted curves, trigonometric and hyperbolic functions, numerical limits, symbolic derivatives, integrals, and numerical roots. Numerical estimates are not mathematical proofs.
- Electronics: 28 devices, a function generator, instruments, wires, rotation, and undo. Isolated local ngspice supports DC, transient analysis, AC/DC sweeps, plots, CSV, and netlists. Device models are educational rather than a Multisim replica.
- Networks: nine devices, cables, VLANs, gateways, interfaces, animated educational ping/traceroute, IP/gateway/link checks, duplication, and grid layout. CIDR host ranges and wildcard masks, equal-size subnetting and VLSM, and reports/tables that can be inserted into a notebook. Multi-selection through Shift-click, long press, or area selection; group movement, Delete, and Undo in circuits and topologies. A show/diagnose/traceroute console. It does not run Cisco IOS or send real packets; routing through multiple routers is not implemented.

See [ALBA-CORE architecture, configuration, and limitations](docs/ALBA_CORE.md) and [Raspberry Pi measurements: eight models, 64 trials, and personal training](docs/PI_INFERENCE_RESULTS.md). These detailed guides are currently in Italian.

## Install on Linux / Raspberry Pi

Recommended hardware: Raspberry Pi 5, 8 GB RAM, 64-bit Linux, and at least 10 GB free for models and data. Setup inspects RAM, CPU, and disk space and selects an initial model. A 750 GB disk is not required; retention is configured in `.env`.

```sh
git clone https://github.com/Dvlce/alba-tramonto.git
cd alba-tramonto
python3 install.py
```

Setup installs Linux dependencies, a Python environment, Ollama if it is missing, the model, and the service. It securely prompts for the BotFather token and administrator ID. You can omit Telegram and create a local administrator from the terminal. Existing `.env` files are preserved. Downloads need internet access during setup; model inference runs locally. Use `--skip-system`, `--no-model`, or `--no-service` for a customized installation.

Initial credentials are written to `data/first-access.txt` with mode `0600`. Read them from the terminal, store them safely, and remove that file. The server listens **only on 127.0.0.1:8088**. Publish it through an HTTPS reverse proxy, set `PUBLIC_URL`, and restart. Tailscale Funnel is one option; web and Telegram users do not need to install Tailscale. Do not expose the Ollama port or the database.

The generated service runs as the installing user. To use a dedicated service account, adapt `deploy/alba.service`. [Security measures](SICUREZZA.md) describes the reference installation in Italian. `deploy/harden_pi.py` is specific to that machine: review and adapt its users and keys before using it elsewhere. General setup does not automatically change SSH or firewall configuration.

The model and backend can be replaced:

```ini
MODEL=qwen3:4b-instruct-2507-q4_K_M
LLM_BACKEND=ollama
LLM_URL=http://127.0.0.1:11434
MAX_USERS=20
MAX_ONLINE=5
```

With 8 GB RAM, a quantized 4B model and SQLite provide a lightweight configuration. Only one generation runs at a time; five chat slots do not mean five loaded models. With less RAM, setup suggests `qwen3:1.7b`. For llama.cpp, use `LLM_BACKEND=llamacpp` and its local OpenAI-compatible endpoint. Measure quality and latency on your hardware before switching models.

## Telegram, web access, and external sign-in

Create a bot with BotFather and provide its token during setup or in `.env`. For groups, enable the required messages in BotFather and add the bot. Supported commands include `/start`, `/help`, `/profile`, `/memory`, `/timeline`, `/search`, `/stats`, `/export`, `/export_key`, `/export_personality`, `/export_prompt`, `/forget`, `/backup`, `/web_key`, `/web_password`, `/feedback`, `/memory_key`, and `/stop`. Administrator commands are separate and operations are audited. An Alba administrator must also be a Telegram administrator of a group to configure it.

In a private chat, `/web_key` creates a personal login button. Its key is carried in the URL fragment, immediately removed from the browser URL, and consumed once. With automatic admission enabled, users can be authorized up to the configured limit of 20. `/web_password` creates or renews personal credentials. Exports require private verification and a single-use key; an administrator cannot recover original passwords or keys. Export files distinguish original data, summaries, inferences, and uncertainty without including other users' private data or unrelated group data.

The administrator can request permission through the panel to inspect a user's memories. That user generates `/memory_key` in their private chat and voluntarily shares the code. The code is single-use, expires after 15 minutes, and grants that administrator a 15-minute inspection window. `/memory_key revoke` revokes codes and access. This permission does not allow exports. Keys and private data are not written to logs.

Google, GitHub, Discord, and SMS sign-in are **available for configuration but disabled without credentials**. See [external sign-in instructions](ACCESSI_ESTERNI.md), currently in Italian. Google uses identity, email, and profile information; it does not read Gmail. To preserve a Telegram identity, sign in with Telegram first and link the provider in Devices.

Terminal commands for the installation operator:

```sh
.venv/bin/python cli.py users
.venv/bin/python cli.py allow ID_TELEGRAM
.venv/bin/python cli.py web-key ID_TELEGRAM
.venv/bin/python cli.py password ID_TELEGRAM
.venv/bin/python maintenance.py backup
```

To restore a backup, stop the service first and run `maintenance.py restore FILE --service-stopped`. Restoration requires the local keys and invalidates previous access. Backups are encrypted and the live database is protected by filesystem permissions. `/forget all confermo` also deletes previous backups on the installation; downloaded copies and Telegram messages must be removed separately.

## Android and integration

Get the APK from [Releases](https://github.com/Dvlce/alba-tramonto/releases), or `/download/alba-albi.apk` when it has been installed on the server. Version 1.3.0 uses a native Android interface without a WebView, with a main chat and dropdown navigation in Italian and English. It includes verified Android App Links for personal Telegram login links. Send `/notte` in Alba's private administrator chat to pair the administrator with autonomous messages.

The native editor saves text, drawing, and JSON while preserving advanced objects. Full labs, images, and A4 PDF remain available in the web portal. The app contains neither personal data nor a bundled LLM and requires a server connection. Its HTTPS server address can be changed in the app. See [Android source and build instructions](android/README.md).

To integrate the engine into an existing system, see [alba-local-kit](https://github.com/Dvlce/alba-local-kit), a Python package with adapters, Telegram integration, and web/CLI keys.

## Validation

```sh
.venv/bin/python -m unittest discover -s tests
```

The automated suite runs on Raspberry Pi and in Linux CI, including four circuits executed in isolated ngspice. Simulator tests require Linux, ngspice, bubblewrap, and available user namespaces.

Browser checks use Playwright and Chromium:

```sh
.venv/bin/python -m pip install playwright
.venv/bin/python -m playwright install chromium
.venv/bin/python tests/portal_motion_browser_check.py
.venv/bin/python tests/notte_browser_check.py
```

Additional checks are available in `tests/browser_check.py`, `tests/tramonto_browser_check.py`, `tests/labs_browser_check.py`, `tests/notebook_editor_check.py`, `tests/appearance_network_check.py`, and `tests/alba_appearance_check.py`. They use temporary databases and do not require LLM calls. Coverage includes identical portal menus and keyboard focus, theme-aware motion, save-before-navigation and failed-save recovery, private/group isolation, denied exports of another user's data, images, A4 printing, reloads, simulations, accounts, CSRF, revocation, and backup/restore.

## Scope and licenses

Alba supports reflection and everyday problem-solving; it is not a clinical or emergency service. Source tracking reduces errors, but a model can still produce inaccurate responses. The installation operator configures privacy information, contact details, access, and maintenance.

Original code is MIT-licensed. Libraries in `vendor/` include their own licenses, and models have separate licenses. The repository contains no application telemetry, personal archives, tokens, or keys.
