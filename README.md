# RamIA CLI Runtime Guide (Blockchain + Wallet Only)

This repository is now focused on **terminal-first usage** of the blockchain and wallet components.

- No static web deployment.
- No Netlify workflow.
- No PWA assets.

If you want to run RamIA reliably, this README is the complete guide.

---

## 1) What is included in this codebase

### Core blockchain engine
- `aichain.py`
  - Minimal blockchain ledger.
  - Mempool + transaction admission.
  - Proof-of-Work mining.
  - CLI commands for init, balance, send, mine, and chain history.

### Tokenomics-enabled chain
- `ramia_core_v1.py`
  - Extends `aichain.ChainDB` with deterministic token emission logic.
  - Tracks pool state in `token_state.json`.
  - CLI commands for `init`, `mine`, and `status`.

- `tokenomics_v1.py`
  - Allocation model and reward math.
  - Includes deterministic self-test mode.

### Wallet and cryptography utilities
- `wallet_secure.py`
  - Encrypted wallet file creation and public identity export.
  - Commands: `create`, `info`, `export-pub`.

- `crypto_backend.py` and `crypto_selftest.py`
  - Crypto provider abstraction and self-tests.

### Optional AI guard / model training
- `aiguardian.py`
  - Train/load guardian model for guarded variants.

- `scripts/make_dataset_demo.sh`
  - Generate a demo dataset for guardian training.

---

## 2) Minimal runtime requirements

- Git
- Python 3.10+ (3.11 recommended)
- pip

> Node.js is no longer required for the CLI-only blockchain/wallet flow.

Check environment:

```bash
git --version
python3 --version
pip3 --version
```

---

## 3) Quick start (all platforms, conceptually)

After cloning the repository, the common flow is:

1. (Optional but recommended) Create virtual environment.
2. Run tokenomics self-test.
3. Initialize chain data.
4. Mine blocks.
5. Send transactions.
6. Inspect balances and chain.
7. (Optional) Create a secure wallet file.

Common command examples:

```bash
python3 tokenomics_v1.py --self-test
python3 aichain.py --datadir ./aichain_data init
python3 aichain.py --datadir ./aichain_data mine miner_demo
python3 aichain.py --datadir ./aichain_data send genesis alice 1000000 --fee 1000 --memo "mempool demo"
python3 aichain.py --datadir ./aichain_data chain --n 10
```

---

## 4) Termux (Android) — full setup

```bash
pkg update -y && pkg upgrade -y
pkg install -y git python
```

Clone:

```bash
git clone <YOUR_REPO_URL>
cd RamIA
```

Optional virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

Run checks + chain:

```bash
python tokenomics_v1.py --self-test
python aichain.py --datadir ./aichain_data init
python aichain.py --datadir ./aichain_data mine miner_termux
python aichain.py --datadir ./aichain_data chain --n 5
```

Secure wallet:

```bash
python wallet_secure.py create --out ./wallet.json --label termux_wallet
python wallet_secure.py info --wallet ./wallet.json
python wallet_secure.py export-pub --wallet ./wallet.json --out ./wallet_public.json
```

---

## 5) Kali Linux — full setup

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
```

Clone + venv:

```bash
git clone <YOUR_REPO_URL>
cd RamIA
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

Run:

```bash
python tokenomics_v1.py --self-test
python aichain.py --datadir ./aichain_data init
python aichain.py --datadir ./aichain_data mine miner_kali
python aichain.py --datadir ./aichain_data balance genesis
```

Tokenomics-enabled mining:

```bash
python ramia_core_v1.py --datadir ./aichain_data_v1 init
python ramia_core_v1.py --datadir ./aichain_data_v1 mine miner_kali
python ramia_core_v1.py --datadir ./aichain_data_v1 status
```

---

## 6) Ubuntu — full setup

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git python3 python3-venv python3-pip
```

Clone + venv:

```bash
git clone <YOUR_REPO_URL>
cd RamIA
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

Run standard chain flow:

```bash
python tokenomics_v1.py --self-test
python aichain.py --datadir ./aichain_data init
python aichain.py --datadir ./aichain_data mine miner_ubuntu
python aichain.py --datadir ./aichain_data send genesis bob 2500000 --fee 1000
python aichain.py --datadir ./aichain_data chain --n 10
```

Run secure wallet utilities:

```bash
python wallet_secure.py create --out ./wallet.json --label ubuntu_wallet
python wallet_secure.py info --wallet ./wallet.json
```

---

## 7) macOS — full setup

Install dependencies (Homebrew):

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install git python
```

Clone + venv:

```bash
git clone <YOUR_REPO_URL>
cd RamIA
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

Run:

```bash
python tokenomics_v1.py --self-test
python aichain.py --datadir ./aichain_data init
python aichain.py --datadir ./aichain_data mine miner_macos
python aichain.py --datadir ./aichain_data chain --n 10
```

---

## 8) Windows (PowerShell) — full setup

Install first:
- Git for Windows
- Python 3.10+ (enable **Add Python to PATH**)

Clone:

```powershell
git clone <YOUR_REPO_URL>
cd RamIA
```

Create + activate virtual environment:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

Run chain and tokenomics:

```powershell
python tokenomics_v1.py --self-test
python aichain.py --datadir .\aichain_data init
python aichain.py --datadir .\aichain_data mine miner_windows
python aichain.py --datadir .\aichain_data chain --n 5
python ramia_core_v1.py --datadir .\aichain_data_v1 init
python ramia_core_v1.py --datadir .\aichain_data_v1 mine miner_windows
python ramia_core_v1.py --datadir .\aichain_data_v1 status
```

Wallet commands:

```powershell
python wallet_secure.py create --out .\wallet.json --label windows_wallet
python wallet_secure.py info --wallet .\wallet.json
python wallet_secure.py export-pub --wallet .\wallet.json --out .\wallet_public.json
```

---

## 9) Useful troubleshooting

- **Transaction appears accepted but later not mined**
  - In the standalone CLI flow, mempool is in-memory per process. If you run `send` and then exit, a later `mine` command in a new process will not include that previous mempool entry.

- **Mining seems slow**
  - This code uses PoW difficulty (`bits`) and can take time depending on CPU and current state.

- **Wallet creation asks for passphrase**
  - This is expected. Use a strong passphrase and keep wallet files private.

- **Reset local chain state**
  - Remove your selected data directory (`./aichain_data` or `./aichain_data_v1`) and initialize again.

---

## 10) Recommended daily CLI workflow

```bash
# 1) validate deterministic math
python3 tokenomics_v1.py --self-test

# 2) mine on base chain
python3 aichain.py --datadir ./aichain_data mine miner_daily

# 3) inspect recent chain
python3 aichain.py --datadir ./aichain_data chain --n 20

# 4) inspect tokenomics chain state
python3 ramia_core_v1.py --datadir ./aichain_data_v1 status
```

This gives you a clean, terminal-native RamIA workflow centered on blockchain and wallet functionality.
