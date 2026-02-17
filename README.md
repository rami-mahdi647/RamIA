# RamIA

RamIA is a local-first AI runtime with wallet, chain, and transaction flows for testing end-to-end behavior.
It combines a local node/dashboard experience for execution with a separate informational PWA for public web presence.
Use this repository to run the stack on your machine, validate core flows, and iterate safely before deployment.

## Architecture (clear split)

- `/site` → informational PWA intended for static hosting (for example, Netlify).
- `node/dashboard` → local runtime surface (wallet, chain, tx, and related node interactions run locally).

In practice, this repo's local runtime is started from Python entrypoints (not from Netlify), while `/site` is the hosted informational frontend.

## Prerequisites

- Git
- Python 3.10+
- Node.js 18+ and npm

Quick check:

```bash
git --version
python3 --version
node --version
npm --version
```

## Quickstart

### Termux

```bash
pkg update -y && pkg upgrade -y
pkg install -y git python nodejs

git clone <REPO_URL>
cd RamIA
npm install
python3 ramia_core_ui.py --guardian-model guardian_model.json --port 8787
```

Then open your browser to `http://127.0.0.1:8787`.

### Desktop (Linux / macOS / Windows)

1. Install Git, Python 3.10+, Node.js 18+.
2. Clone and install dependencies:

```bash
git clone <REPO_URL>
cd RamIA
npm install
```

3. Run RamIA locally:

```bash
python3 ramia_core_ui.py --guardian-model guardian_model.json --port 8787
```

Windows PowerShell equivalent (if needed):

```powershell
py -3 ramia_core_ui.py --guardian-model guardian_model.json --port 8787
```

Open `http://127.0.0.1:8787` after startup.

## QA checklist

Use this list for a basic end-to-end sanity pass:

- [ ] Create wallet
- [ ] Mine / get coins
- [ ] Send transaction
- [ ] View transaction + mempool
- [ ] Open Stripe link

## Notes

- Keep `/site` focused on informational/public PWA content.
- Keep node/dashboard behaviors in the local runtime path for development and QA.
