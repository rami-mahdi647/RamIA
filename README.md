RamIA Core — Developer Guide (Terminal Edition)

A terminal-first node implementation inspired by the “Core” workflow: you run a local node, manage data directories, mine/test blocks, create transactions, and inspect chain state from the command line.

> This is developer software. Expect breaking changes. Run locally first.




---

Contents

What is RamIA Core

Quickstart

Data directory layout

Commands

Termux / Linux / macOS / Windows setup

Troubleshooting

Security notes



---

What is RamIA Core

RamIA Core is a local node you run on your own machine. It maintains a chain database under a data directory and exposes a terminal workflow similar to “core clients”:

initialize a datadir

mine blocks (dev/test)

create and broadcast transactions

inspect chain state


At the moment, the repository ships a single chain engine script:

aichain.py — local chain + mining + tx send + chain inspection


(If you’ve seen references to tokenomics_v1.py, wallet_secure.py, etc., those are optional modules and may not exist in your current repo snapshot.)


---

Quickstart (5 minutes)

Termux / Linux / macOS

cd ~
rm -rf RamIA
git clone https://github.com/rami-mahdi647/RamIA.git
cd RamIA

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip

# 1) Initialize chain data directory
python3 aichain.py --datadir ./aichain_data init

# 2) Mine 1 block (dev/test)
python3 aichain.py --datadir ./aichain_data mine miner_dev

# 3) Send a test transaction
python3 aichain.py --datadir ./aichain_data send genesis alice 1000000 --fee 1000 --memo "hello"

# 4) Inspect chain
python3 aichain.py --datadir ./aichain_data chain --n 10

Windows (PowerShell)

cd $HOME
if (Test-Path RamIA) { Remove-Item -Recurse -Force RamIA }
git clone https://github.com/rami-mahdi647/RamIA.git
cd RamIA

py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install --upgrade pip

py aichain.py --datadir .\aichain_data init
py aichain.py --datadir .\aichain_data mine miner_dev
py aichain.py --datadir .\aichain_data send genesis alice 1000000 --fee 1000 --memo "hello"
py aichain.py --datadir .\aichain_data chain --n 10


---

Data directory

All chain state lives under --datadir (similar to how core clients keep chainstate under a single data dir).

Example:

./aichain_data/


To start fresh:

rm -rf ./aichain_data
python3 aichain.py --datadir ./aichain_data init


---

Command reference (current)

Initialize

python3 aichain.py --datadir ./aichain_data init

Mine (dev/test)

python3 aichain.py --datadir ./aichain_data mine <miner_label_or_address>

Notes:

On Termux, mining can be slow (phone CPU). Stop with Ctrl+C.


Send transaction

python3 aichain.py --datadir ./aichain_data send <from> <to> <amount> --fee <fee> --memo "<text>"

Example:

python3 aichain.py --datadir ./aichain_data send genesis alice 1000000 --fee 1000 --memo "mempool demo"

Inspect chain

python3 aichain.py --datadir ./aichain_data chain --n 20


---

Platform setup

Termux

pkg update -y
pkg install -y python git

Then follow Quickstart (Termux/Linux/macOS).

Linux (Ubuntu/Kali)

sudo apt update
sudo apt install -y python3 python3-venv git

macOS

Install Python and git (recommended via Homebrew):

brew install python git

Windows

Install Python 3 from python.org

Install Git for Windows (recommended)



---

Troubleshooting

git clone <[>](https://...) fails

That’s a formatted link, not a shell command.

✅ Correct command:

git clone https://github.com/rami-mahdi647/RamIA.git

can't open file ... tokenomics_v1.py (or wallet_secure.py / ramia_core_v1.py)

Those files are not present in your current repo snapshot.

Check:

ls -la tokenomics_v1.py wallet_secure.py ramia_core_v1.py 2>/dev/null || echo "missing optional files"

Use only commands that match files that exist (Quickstart uses aichain.py only).

Mining is slow on Termux

Expected. PoW on mobile can take time.

Options:

run on desktop

mine fewer blocks

(future) add a lower difficulty/dev mode flag in code



---

Security notes (developer)

Never paste wallet files or keys into chat or issues.

Do not commit secrets. Add to .gitignore:

aichain_data/

wallet*.json

*.key

*.bin

*.jsonl




---

Development philosophy (Core-like)

Terminal-first

One datadir

Small, auditable code paths

Build features only when they run end-to-end locally:

1. wallet → 2) tx → 3) mempool → 4) blocks → 5) policies (guardian/fees) → 6) bot leasing





---

If you want, I can also write a ramia-cli wrapper (single command like bitcoin-cli) so you stop calling aichain.py directly—still terminal-only, still “Core-like”.
