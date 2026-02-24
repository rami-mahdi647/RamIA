# RamIA

Terminal-first blockchain + AI-guarded transaction workflows, with auditable reward logs and optional secure wallet/Stripe integrations.

This repository is designed to be usable by people who work directly in a terminal (Linux, Kali Linux, Termux, macOS, WSL). It includes a lightweight chain core, wrappers for safer UX, and optional modules for stronger wallet security and payment bridging.

---

## 1) What RamIA is

RamIA is a local-first prototype stack centered on:

- **`aichain.py`**: minimal blockchain engine (state, mempool, PoW mining, balances, chain inspection).
- **`ramia_node.py`**: operator CLI wrapper that adds deterministic AI risk checks and reward logging on top of `aichain.py`.
- **`ramia_ai_guardian.py`**: deterministic risk scoring + policy decision (`allow`, `warn`, `fee_multiplier`, `reject`).
- **`ramia_reward_policy.py`** + **`ramia_rewards_ledger.py`**: deterministic reward calculation and append-only hash-chained reward events.
- **Secure/advanced modules** like `wallet_secure.py`, `ramia_core_secure.py`, and `stripe_webhook.py` for wallet hardening and payment-based grant flows.

> Status: this is a prototype/developer-oriented system, not a production blockchain.

---

## 2) How it works (high level)

1. You initialize chain state (`aichain_data/`) with `aichain.py init` or `ramia_node.py init`.
2. You mine blocks (`mine`) to advance chain height and create miner rewards.
3. You send transactions (`send`) from one address string to another.
4. If you use `ramia_node.py send`, the **AI Guardian** scores the transaction first.
5. When mining via `ramia_node.py mine`, a deterministic reward event is appended to:
   - `aichain_data/rewards_ledger.jsonl`
6. Reward ledger integrity is auditable through hash chaining (`prev_hash` → `entry_hash`).

---

## 3) Repository structure (practical map)

### Core runtime

- `aichain.py` → canonical chain CLI and state machine.
- `ramia_node.py` → terminal wrapper around `aichain.py`.
- `ramia_config.json` → runtime config for node, guardian policy, rewards/tokenomics.
- `run_node.sh` → continuous mine loop + log management.
- `run_tmux.sh` → starts persistent mining in a tmux session.

### AI/policy/rewards

- `ramia_ai_guardian.py` → deterministic tx risk model.
- `ramia_reward_policy.py` → bounded deterministic reward function.
- `ramia_rewards_ledger.py` → append/verify reward ledger records.
- `ramia_autopolicy.py`, `ramia_policy_service.py` → policy-oriented extensions.

### Security and wallet

- `wallet_secure.py`, `ramia_wallet_secure.py` → encrypted wallet file workflows.
- `crypto_backend.py`, `crypto_selftest.py`, `tx_privacy.py` → crypto primitives and checks.
- `ramia_core_secure.py`, `ramia_core.py` → secure runtime entrypoint.
- `SECURITY.md`, `docs/CRYPTO_SPEC.md`, `docs/THREAT_MODEL.md` → security model/docs.

### Payment bridge (optional)

- `stripe_webhook.py`, `stripe_bridge.py`, `STRIPE_SETUP.md`.

### Documentation and tests

- `INSTALL.md`, `docs/*.md` for product and architecture notes.
- `tests/` with selected unit/integration checks.

### Vendored subproject

- `vendor/quantumcore/` contains a larger web/desktop/smart-contract stack with its own tooling and docs.

---

## 4) Prerequisites (terminal users)

Minimum for core CLI usage:

- **Git**
- **Python 3.10+** (3.11/3.12 recommended)
- **tmux** (optional but recommended for persistent node sessions)

### Optional Python packages (only for advanced features)

Core chain + basic RamIA wrapper mainly uses standard library. Install these only if you use related modules:

- `cryptography` (secure wallet AEAD/Ed25519 paths)
- `argon2-cffi` (stronger KDF path in wallet creation)
- `flask` + `stripe` (Stripe webhook service)

If you want all optional features available:

```bash
python3 -m pip install --upgrade pip
python3 -m pip install cryptography argon2-cffi flask stripe
```

---

## 5) OS-specific installation

## Kali Linux (recommended path for your request)

```bash
sudo apt update
sudo apt install -y git python3 python3-pip tmux
python3 -m pip install --upgrade pip
```

Then clone and run Quickstart below.

## Debian / Ubuntu

```bash
sudo apt update
sudo apt install -y git python3 python3-pip tmux
python3 -m pip install --upgrade pip
```

## Fedora

```bash
sudo dnf install -y git python3 python3-pip tmux
python3 -m pip install --upgrade pip
```

## Arch Linux

```bash
sudo pacman -Sy --needed git python python-pip tmux
python -m pip install --upgrade pip
```

## macOS (Homebrew)

```bash
brew install git python tmux
python3 -m pip install --upgrade pip
```

## Termux (Android)

Use the included script:

```bash
pkg update -y && pkg upgrade -y
pkg install -y git

git clone <YOUR_REPO_URL>
cd RamIA
bash scripts/termux_install.sh
```

Or manually:

```bash
pkg update -y && pkg upgrade -y
pkg install -y python git tmux
python -m pip install --upgrade pip
```

## Windows users (terminal/professional workflow)

Use **WSL2** with Ubuntu/Kali and follow Linux steps above.

---

## 6) Clone the repository

Replace with your actual repository URL:

```bash
git clone <YOUR_REPO_URL>
cd RamIA
```

If you use SSH:

```bash
git clone git@github.com:<your-org-or-user>/RamIA.git
cd RamIA
```

---

## 7) Quickstart (core terminal workflow)

### A) Initialize local chain data

```bash
python3 ramia_node.py init
```

### B) Mine one block

```bash
python3 ramia_node.py mine miner_1
```

### C) Show recent chain

```bash
python3 ramia_node.py chain --n 10
```

### D) Send a transaction (AI-guarded path)

```bash
python3 ramia_node.py send alice bob 10 --fee 0.01 --memo "hello"
```

### E) Check balance directly in chain core

```bash
python3 aichain.py balance bob
# or explicitly
python3 aichain.py --datadir ./aichain_data balance bob
```

---

## 8) CLI command reference

## `aichain.py` (core)

```bash
python3 aichain.py --datadir ./aichain_data init
python3 aichain.py --datadir ./aichain_data balance <ADDR>
python3 aichain.py --datadir ./aichain_data send <FROM> <TO> <AMOUNT_INT> --fee <FEE_INT> --memo "..."
python3 aichain.py --datadir ./aichain_data mine <MINER_ADDR>
python3 aichain.py --datadir ./aichain_data chain --n 20
```

Important: in `aichain.py`, `amount` and `fee` are integer units.

## `ramia_node.py` (wrapper)

```bash
python3 ramia_node.py init
python3 ramia_node.py mine <MINER>
python3 ramia_node.py chain --n 10
python3 ramia_node.py send <SENDER> <TO> <AMOUNT> --fee <FLOAT_OR_INT> --memo "..."
python3 ramia_node.py score '{"from":"a","to":"b","amount":1}'
python3 ramia_node.py reward 1.0 '{"from":"a","to":"b","amount":1}'
```

Wrapper fee normalization uses:

- `ramia_config.json` → `node.fee_unit`

---

## 9) Persistent operation in terminal (tmux)

Start loop (includes init + mine + reward ledger verify):

```bash
./run_tmux.sh miner_1
```

Attach:

```bash
tmux attach -t ramia
```

Detach without stopping:

- `Ctrl+B`, then `D`

Stop session:

```bash
tmux kill-session -t ramia
```

---

## 10) Logs and data locations

Default paths:

- Chain data: `./aichain_data/`
- Logs: `./logs/`

Common logs produced by run scripts:

- `logs/supervisor.log`
- `logs/init.log`
- `logs/mine.log`
- `logs/ledger_verify.log`

Tail mining logs:

```bash
tail -f logs/mine.log
```

---

## 11) Rewards and audit trail

Reward ledger file:

- `aichain_data/rewards_ledger.jsonl`

Integrity fields include:

- `prev_hash`
- `entry_hash`

Verify reward ledger integrity:

```bash
python3 ramia_rewards_ledger.py
```

Reward policy sources:

- `ramia_reward_policy.py`
- `ramia_config.json` (`tokenomics`, `network_metrics`)

---

## 12) Security-focused usage

For hardened wallet/runtime flows, review and use:

- `wallet_secure.py`
- `ramia_core_secure.py`
- `SECURITY.md`
- `docs/CRYPTO_SPEC.md`

Example wallet utility commands:

```bash
python3 wallet_secure.py create --out wallet.secure.json --label operator
python3 wallet_secure.py info --wallet wallet.secure.json
python3 wallet_secure.py export-pub --wallet wallet.secure.json
```

---

## 13) Optional Stripe integration

If you need payment/grant flows:

1. Read `STRIPE_SETUP.md`.
2. Install optional deps (`flask`, `stripe`).
3. Configure required Stripe environment variables.

Main bridge files:

- `stripe_webhook.py`
- `stripe_bridge.py`

---

## 14) Health checks and tests

Self-test examples from this repo:

```bash
python3 tokenomics_v1.py --self-test
python3 crypto_selftest.py
```

Pytest suite (if you have pytest installed):

```bash
python3 -m pytest -q
```

---

## 15) Professional terminal workflow recommendations

- Use a dedicated Python virtual environment per deployment.
- Keep `ramia_config.json` versioned and reviewed.
- Run node in `tmux`/`screen` (or a systemd service in Linux servers).
- Back up `aichain_data/` and secure wallet files regularly.
- Do not commit secrets, wallet files, or Stripe secrets.
- For Kali/Linux operator environments, prefer non-root runtime and strict file permissions.

---

## 16) Known limitations

- Prototype architecture (not production consensus/networking).
- Mining, mempool, and policy logic are intentionally simplified.
- Some modules are optional/experimental and require extra dependencies.

---

## 17) Further docs

- `INSTALL.md`
- `SECURITY.md`
- `docs/FAQ.md`
- `docs/MVP_FLOW.md`
- `docs/PRODUCT_V1.md`
- `docs/THREAT_MODEL.md`
- `docs/TOKENOMICS_V1.md`
- `docs/V1_2_RELEASE_PLAN.md`

