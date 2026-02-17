# RamIA Core (Developer Edition) — Terminal-First AI-Guarded Chain

RamIA is a terminal-first blockchain prototype designed for fast iteration by developers: initialize a local chain, mine/test blocks, submit transactions, and inspect chain state — with an optional AI “Guardian” layer for spam/risk scoring and policy hooks.

> **Audience:** Developers / researchers.  
> **Status:** Prototype / experimental.  
> **Security:** Do not use with real money. Do not reuse production keys.

---

## Why this exists (technical goal)

RamIA focuses on a minimal “Core-like” workflow, then layers in policy and automation:

- Core chain loop: blocks, transactions, PoW mining (dev/test), mempool/fees.
- AI policy hooks: transaction scoring + fee penalties + human-readable “why”.
- Bot-fleet simulation: an AI-worker fleet & rental/market modules to model capacity.
- Security building blocks: wallet encryption-at-rest, AEAD primitives, privacy payload scaffolding.
- Payments hooks (optional): Stripe webhook → “grant token” → local node redemption.

---

## Technical innovations (what’s different)

### 1) AI Guardian (spam/risk filter)

A lightweight, pure-Python classifier pipeline:

- CSV training (`aiguardian.py train`)
- deterministic inference (`aiguardian.py score`)

Designed as a clean hook to:

- warn before broadcast
- apply fee multipliers for suspicious patterns
- generate reasons/suggestions (explainability scaffolding)

### 2) AI Fleet / Bot Market modules

Files like `aichain_aifleet*.py` and `aichain_aifleet_market*.py` model:

- “bots” as capacity providers
- market/orderbook patterns (secure orderbook variants present)
- stateful fleet simulation and SLA scaffolding

### 3) Tokenomics v1 (deterministic)

`tokenomics_v1.py` provides deterministic math + a self-test harness to keep monetary logic reproducible.

### 4) Wallet/key security scaffolding

`crypto_backend.py`, `crypto_selftest.py`, `wallet_secure.py` provide:

- a backend interface for safe primitives (AEAD, signing)
- a self-test script to validate crypto round-trips
- encrypted wallet storage (where supported by available libs)

### 5) Optional Stripe automation flow (developer only)

`stripe_webhook.py` + `stripe_bridge.py` are intended to support:

- payment confirmation → issuance of an activation/grant token
- local node redemption via an adapter entrypoint

> Stripe automation needs a webhook endpoint; this is not a “static site” feature.

---

## Repository map (high level)

### Core chain & CLI

- `aichain.py` — base chain engine (`init` / `mine` / `send` / `chain`)
- `aichain_guarded*.py` — guarded policy variants (warning/notice v2 variants)

### AI

- `aiguardian.py` — train/score pipeline (pure Python)

### Tokenomics

- `tokenomics_v1.py` — deterministic tokenomics + self-test
- `ramia_core_v1.py` — tokenomics wrapper/entrypoint

### Security & privacy

- `crypto_backend.py`, `crypto_selftest.py`
- `wallet_secure.py` — secure wallet tooling
- `tx_privacy.py` — private payload scaffolding

### Node extensions / adapters

- `aicore_plus.py`, `ramia_core_plus.py`, `ramia_core_ui.py`, `ramia_core.py`

> Some web/UI entrypoints may require a UI HTML file not included in every snapshot.

### Docs

- `INSTALL.md`, `SECURITY.md`, `STRIPE_SETUP.md`, `docs/`

### Scripts

- `scripts/termux_install.sh`
- `scripts/termux_run.sh`

---

## Quickstart (Termux / Linux / macOS / Windows)

### 0) Requirements

- Python 3.10+ recommended (Termux ships 3.12+)
- Git

### Termux (Android)

Install dependencies:

```bash
pkg update -y && pkg upgrade -y
pkg install -y python git
python -m pip install --upgrade pip
```

Clone + run demo:

```bash
cd ~
rm -rf RamIA
git clone https://github.com/rami-mahdi647/RamIA.git
cd RamIA

# Optional convenience scripts
bash ./scripts/termux_run.sh
```

Manual (same as script):

```bash
python3 tokenomics_v1.py --self-test
python3 aichain.py --datadir ./aichain_data init
python3 aichain.py --datadir ./aichain_data mine miner_termux
python3 aichain.py --datadir ./aichain_data chain --n 5
```

### Linux (Ubuntu/Kali/etc.)

Install system deps:

```bash
sudo apt update
sudo apt install -y python3 python3-venv git
```

Clone + run:

```bash
cd ~
rm -rf RamIA
git clone https://github.com/rami-mahdi647/RamIA.git
cd RamIA

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip

python3 tokenomics_v1.py --self-test
python3 aichain.py --datadir ./aichain_data init
python3 aichain.py --datadir ./aichain_data mine miner_linux
python3 aichain.py --datadir ./aichain_data chain --n 10
```

### macOS

Install deps (Homebrew):

```bash
brew install python git
```

Clone + run:

```bash
cd ~
rm -rf RamIA
git clone https://github.com/rami-mahdi647/RamIA.git
cd RamIA

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip

python3 tokenomics_v1.py --self-test
python3 aichain.py --datadir ./aichain_data init
python3 aichain.py --datadir ./aichain_data mine miner_macos
python3 aichain.py --datadir ./aichain_data chain --n 10
```

### Windows (PowerShell)

Clone + run:

```powershell
cd $HOME
if (Test-Path RamIA) { Remove-Item -Recurse -Force RamIA }
git clone https://github.com/rami-mahdi647/RamIA.git
cd RamIA

py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install --upgrade pip

py tokenomics_v1.py --self-test
py aichain.py --datadir .\aichain_data init
py aichain.py --datadir .\aichain_data mine miner_windows
py aichain.py --datadir .\aichain_data chain --n 10
```

If `py` is not available, use `python` from your `PATH`.

---

## Core commands (CLI)

Initialize chain:

```bash
python3 aichain.py --datadir ./aichain_data init
```

Mine a block (dev/test PoW):

```bash
python3 aichain.py --datadir ./aichain_data mine miner_demo
```

Send a transaction:

```bash
python3 aichain.py --datadir ./aichain_data send genesis alice 1000000 --fee 1000 --memo "hello"
```

Inspect last N blocks:

```bash
python3 aichain.py --datadir ./aichain_data chain --n 20
```

---

## AI Guardian (train + score)

Create a tiny demo dataset:

```bash
cat > dataset.csv << 'CSV'
amount,fee,outputs,memo,to_addr,burst_score,timestamp,label
100000,1000,1,hello,abcd1234,0.1,1700000000,0
250000,50,6,FREE MONEY NOW!!!,zzzzzzzzzzzzzzzz,0.9,1700003600,1
50000,800,1,payment,a1b2c3d4e5,0.2,1700007200,0
900000,10,10,airdrop claim,http://spammy.link,1.0,1700010800,1
CSV
```

Train the model:

```bash
python3 aiguardian.py train --csv dataset.csv --out guardian_model.json
```

Score a transaction (example JSON):

```bash
python3 aiguardian.py score --model guardian_model.json --tx-json '{
  "amount": 250000,
  "fee": 50,
  "outputs": 6,
  "memo": "FREE MONEY NOW!!!",
  "to_addr": "zzzzzzzzzzzzzzzz",
  "burst_score": 0.9,
  "timestamp": 1700003600
}'
```

---

## Crypto self-test (optional)

If your environment supports the crypto backend:

```bash
python3 crypto_selftest.py
```

If Termux cannot build heavy crypto wheels (common), keep running the chain + guardian in pure-python mode.

---

## Troubleshooting

### “git clone …” errors with brackets/parentheses

Do not paste formatted links like:

```bash
git clone <[>](https://github.com/...)
```

Use the raw URL:

```bash
git clone https://github.com/rami-mahdi647/RamIA.git
```

### Mining feels slow on mobile

Expected with PoW. Use desktop for faster iteration or reduce mining usage during development.

### UI/web runner errors (missing HTML)

Some web-mode runners may reference an HTML file not present in all snapshots. This repo is intended to be terminal-first. If you want a local dashboard, add a UI file or use a stable runner that includes assets.

---

## Security notes (read this)

- Never commit wallet files or secrets.
- Don’t paste keys into chats/issues.
- Use `.gitignore` for:
  - `aichain_data/`
  - `wallet*.json`
  - `*.key`
  - `*.bin`
  - `*.jsonl`

See `SECURITY.md` for the full policy.

---

## Contributing (developer workflow)

```bash
git pull
python3 tokenomics_v1.py --self-test
python3 aichain.py --datadir ./aichain_data chain --n 5
```

Open PRs should include:

- a short design note (what changes, why)
- minimal test steps that reproduce behavior
