# RamIA — Developer Runtime Guide

This repository README is for technical users who want to run RamIA from the terminal on local machines (Linux, Ubuntu, macOS, and Windows).

> Focus: running the software stack locally (node process + local web/API surface). This is not a marketing or Netlify-first guide.

## What this repository contains

- `ramia_core_plus.py`: main local runtime entrypoint (web server + local API routes).
- `aicore_plus.py`: local application context and handler stack used by `ramia_core_plus.py`.
- `aichain.py`, `ramia_core.py`, `ramia_core_v1.py`: chain/runtime variants and related CLI flows.
- `ui_plus.html`: local UI served by the runtime.
- `site/`: static web assets for hosted/browser-facing frontend.

## Prerequisites

- Git
- Python 3.10+
- Node.js 18+ and npm (required for JS dependencies used in this repo)

Check your environment:

```bash
git --version
python3 --version
node --version
npm --version
```

## Clone and install

```bash
git clone <REPO_URL>
cd RamIA
npm install
```

---

## Platform setup

### Linux (generic)

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip nodejs npm
```

Then run:

```bash
git clone <REPO_URL>
cd RamIA
npm install
python3 ramia_core_plus.py --guardian-model ./guardian_model.json --web --web-host 127.0.0.1 --web-port 8787
```

### Ubuntu (recommended flow)

1) Install dependencies:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl python3 python3-venv python3-pip nodejs npm
```

2) Clone and install:

```bash
git clone <REPO_URL>
cd RamIA
npm install
```

3) Start local runtime:

```bash
python3 ramia_core_plus.py \
  --guardian-model ./guardian_model.json \
  --web \
  --web-host 127.0.0.1 \
  --web-port 8787
```

### macOS

Install tools (Homebrew):

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install git python node
```

Run:

```bash
git clone <REPO_URL>
cd RamIA
npm install
python3 ramia_core_plus.py --guardian-model ./guardian_model.json --web
```

### Windows (PowerShell)

Install first:
- Git for Windows
- Python 3 (enable **Add python.exe to PATH**)
- Node.js LTS

Then run:

```powershell
git clone <REPO_URL>
cd RamIA
npm install
py -3 ramia_core_plus.py --guardian-model .\guardian_model.json --web --web-host 127.0.0.1 --web-port 8787
```

### Windows option: WSL2 + Ubuntu

If you prefer a Linux-like workflow on Windows, use WSL2 Ubuntu and follow the Ubuntu section above.

---

## Running the software

## Main runtime command

```bash
python3 ramia_core_plus.py --guardian-model ./guardian_model.json --web
```

Useful flags:

- `--datadir <path>`: chain/state directory.
- `--web`: force-enable local web server.
- `--no-web`: disable local web server.
- `--web-host <host>`: bind host (default from config, commonly `127.0.0.1`).
- `--web-port <port>`: bind port (default commonly `8787`).
- `--conf <path>`: use custom runtime config file.

## Local endpoint contract

When the runtime is started with web enabled, it exposes:

- `POST /api/redeem_grant`

Request body:

```json
{
  "renter": "demo",
  "token": "<grant_token>"
}
```

Example request:

```bash
curl -X POST http://127.0.0.1:8787/api/redeem_grant \
  -H 'Content-Type: application/json' \
  -d '{"renter":"demo","token":"<grant_token_here>"}'
```

---

## Minimal terminal verification

Run these after setup:

```bash
python3 ramia_core_plus.py --help
python3 ramia_core.py --help
python3 ramia_core_v1.py --help
```

If those CLI help commands work, your Python runtime and script entrypoints are correctly discovered.

---

## Troubleshooting

- `python3: command not found`
  - Python is not installed or not in PATH.
- `py : The term 'py' is not recognized` (Windows)
  - Reinstall Python and ensure launcher/PATH integration is enabled.
- `Error: Cannot find module ...` (Node)
  - Run `npm install` in repo root.
- Port already in use (`8787`)
  - Start with `--web-port 8788` (or any free port).
- Runtime fails to boot due to missing files
  - Confirm `guardian_model.json` and `ui_plus.html` exist at expected paths.

---

## Recommended developer workflow

1. Install dependencies and clone the repo.
2. Validate CLI entrypoints with `--help`.
3. Start `ramia_core_plus.py` with explicit host/port.
4. Hit local endpoints using `curl`.
5. Iterate with custom `--datadir` and `--conf` profiles.
