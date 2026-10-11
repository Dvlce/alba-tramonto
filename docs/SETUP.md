# One-file setup for a fresh machine

Download **one file for your operating system** from the [Setup v1.0.2 release](https://github.com/Dvlce/alba-tramonto/releases/tag/setup-v1.0.2). Each file embeds the same Alba, Tramonto and Notte application sources, browser libraries, fonts and public documentation. You do not need Git or a repository checkout. Internet access is needed for Python, dependencies, Ollama and model downloads; this is not an offline model bundle.

| System | Download | Run from the download directory |
|---|---|---|
| Linux 64-bit: Debian, Ubuntu, Raspberry Pi OS | [alba-setup-linux.sh](https://github.com/Dvlce/alba-tramonto/releases/download/setup-v1.0.2/alba-setup-linux.sh) | `sh alba-setup-linux.sh` |
| macOS: Apple Silicon or Intel, macOS 14+ for Ollama | [alba-setup-macos.command](https://github.com/Dvlce/alba-tramonto/releases/download/setup-v1.0.2/alba-setup-macos.command) | `sh alba-setup-macos.command` |
| Windows 10/11 64-bit | [alba-setup-windows.ps1](https://github.com/Dvlce/alba-tramonto/releases/download/setup-v1.0.2/alba-setup-windows.ps1) | `powershell -NoProfile -ExecutionPolicy Bypass -File .\alba-setup-windows.ps1` |

Run as the user who will own the installation. Linux asks for sudo when installing packages and its systemd service. macOS asks for an administrator password only if Python must be installed. Windows installs Python and Ollama for the current user. Do not run the Windows setup as another administrator account.

The setup checks for a usable Python 3.10+ interpreter. If missing, Linux uses the distribution package manager; Windows and macOS download Python 3.13.16 from python.org and verify its SHA-256. It then verifies the embedded application archive and every file against its manifest, creates a private Python environment, installs runtime dependencies and Ollama if needed, and downloads the initial chat, Notte, coding and embedding models. The larger chat model is selected with at least 6 GiB RAM. Allow at least 10 GB of free storage for the standard models; weight training needs additional space and preferably 8 GB RAM.

## First access

Telegram is optional. Leave the BotFather token and administrator ID blank to create a local administrator. The optional public URL must use HTTPS. Secrets are entered through the terminal, never through command-line arguments.

Open **http://127.0.0.1:8088** after setup. Read the username and random password from `data/first-access.txt` inside the installation directory, save them privately, then remove that file. The private learning panel is `/notte#learning`.

Default directories:

- Linux: `~/alba-tramonto`
- macOS: `~/Library/Application Support/Alba`
- Windows: `%LOCALAPPDATA%\Alba`

Use `--directory PATH` to choose another directory. Linux service paths must not contain spaces, quotes or `%`; use `--no-service` and the manual launcher for such paths. macOS and Windows support their normal paths containing spaces.

The server listens on loopback. To use it from a phone or another computer, configure `PUBLIC_URL` and an HTTPS reverse proxy or Tailscale publishing. This setup does not change SSH, firewall rules, domains or remote accounts.

## Startup and repeat runs

Linux uses `alba.service`. macOS uses the current user's `local.alba.portal` LaunchAgent. Windows uses a current-user Startup shortcut; it starts when that user signs in. All three platforms also get a manual launcher: `start-alba.sh` or `Start Alba.cmd`.

Running the **same setup file** again can resume an interrupted extraction and dependency download. It preserves `.env`, administrator credentials, encryption keys, notebooks, lessons and the database. A different embedded code version is refused in a populated directory: this is a fresh-machine installer, not a replacement for the backed-up production deployment procedure.

The bundle contains public application code. It does not contain the existing machine's accounts, keys, conversations, notebooks, taught lessons, LoRA adapters or model weights. Moving those private files is a separate backup/restore operation.

## Options and platform capabilities

| Option | Behavior |
|---|---|
| `--plan` | Print the destination and installation plan without creating files or installing software. |
| `--extract-only PATH` | Verify and extract sources; skip dependencies, configuration, models and autostart. |
| `--unattended` | Create a web-only local administrator without interactive Telegram/public-URL prompts. |
| `--skip-system` | OS dependencies and Ollama are already installed. |
| `--no-model` | Skip Ollama installation and all model downloads. Useful for installation testing. |
| `--no-service` | Skip autostart and create only the manual launcher. |
| `--with-training` | Prepare the optional isolated Notte LoRA environment on supported Linux hosts. |

Chat, notebooks, teaching, persistent source memory, public Wikipedia/GitHub imports and the learning dashboard work on all three systems. **Isolated code execution, SPICE and local LoRA weight training currently require Linux.** Those features do not execute downloaded code without their sandbox on macOS/Windows. The optional SSD research runtime and WhatsApp bridge have their own preparation procedures and are not installed by this bundle.

For weight training, use `--with-training` on Linux ARM64 with Python 3.13, or Linux x86_64 with Python 3.10–3.13. The setup checks compatibility before installing dependencies or downloading models, then prepares the pinned public Qwen 0.5B base, separate CPU Torch/PEFT environment and llama.cpp quantizer. Existing private trained adapters are not distributed.

Example: `sh alba-setup-linux.sh --with-training`.

## Build and verification

From a checked-out repository, run `python3 tools/build_setup.py`. Only tracked, allowlisted public source paths are packaged; `.env`, data, backups, machine-specific deployment scripts and private WhatsApp credentials are excluded. The reproducible installers and `SHA256SUMS.txt` are written to `dist/setup/`.

The **Portable setup** CI workflow installs the bundle in a temporary directory on Linux, Windows and macOS, starts the native portal, logs in with its newly generated administrator, saves a persistent lesson, and verifies that rerunning setup retains credentials and encryption keys. Models and OS autostart are excluded from this smoke test. Installer unit tests cover malformed archives, path traversal, symlinks, changed code, configuration preservation and URL validation.

Runtime download references: [Python 3.13.16](https://www.python.org/downloads/release/python-31316/), [Ollama Windows](https://docs.ollama.com/windows), [Ollama macOS](https://docs.ollama.com/macos).

The setup includes keyless Stack Overflow and JokeAPI readers for Python/web and humor. Public-source reading creates searchable knowledge; their texts do not enter weight training. Reddit access remains optional and limited by the platform. See [Notte learning](NOTTE_LEARNING.md).
