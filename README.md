# AIChain Core (AI-Fleet + Guardian + Local UI)

AIChain Core is a **downloadable, local-first** prototype inspired by *Bitcoin Core*:
- **CLI-first** for technical users
- Optional **local Web UI** (runs on `localhost`, no hosting)
- An **AI committee (“AI Fleet”)** that gates mempool admission and helps drive policy
- A **Guardian** ML model (you train it) that scores transaction risk/spam
- A **GPU-style renting marketplace** (spot orderbook + reserved contracts)
- **Metering** via credits (service units consumed per screening)
- **Medium security**: API keys, anti-replay, tamper-evident state + audit hash-chain
- **Privacy receipts (stub)** for rejected/quarantined transactions (upgradeable to real ZK)

> ⚠️ This is a prototype. It is intentionally minimal and designed to evolve.  
> “ZK” is currently a stub: commitment + proof placeholder.

---

## Repository Layout

Minimum required files:

- `aicore.py` *(single-file app: CLI + local Web UI + patches)*
- `aichain.py` *(your chain engine)*
- `aiguardian.py` *(Guardian model code, training + inference)*

Outputs generated at runtime (default):
- `./aichain_data/` (chain data)
- `./guardian_model.json` (Guardian model)
- `./fleet_state.json` (AI Fleet state)
- `./burst_state.json` (burst-rate tracking)
- `./market_secure_state.bin` (market state, sealed)
- `./market_secret.key` (master secret for sealing/signing)
- `./audit_log.jsonl` (hash-chained audit log)

---

## Requirements

- Python 3.10+ recommended
- No external web hosting needed

Optional:
- `cryptography` for encrypting sealed state at rest:
  ```bash
  pip install cryptography

If cryptography is not installed, state remains HMAC-protected (tamper-evident) and stored with best-effort 0600 permissions.


---

Quick Start

1) Train Guardian

Prepare a CSV dataset (your own) and train:

python3 aiguardian.py train --csv dataset.csv --out guardian_model.json

2) Initialize the chain

python3 aicore.py --guardian-model guardian_model.json init

3) Run as a local node (Bitcoin Core style)

CLI-only:

python3 aicore.py --guardian-model guardian_model.json node

CLI + Local Web UI:

python3 aicore.py --guardian-model guardian_model.json node --web

Then open:

http://127.0.0.1:8787



---

CLI Usage

Send a transaction

python3 aicore.py --guardian-model guardian_model.json send genesis alice 100000 --fee 1000 --memo "hello"

If rejected/quarantined, you’ll receive a privacy receipt (commitment + stub proof).
If you want private sender hints, run with:

python3 aicore.py --guardian-model guardian_model.json --privacy-mode reveal_to_sender send genesis alice 100000

Mine a block

python3 aicore.py --guardian-model guardian_model.json mine x

> Note: x is ignored. The fleet selects a miner bot internally.



View top fleet stats

python3 aicore.py --guardian-model guardian_model.json stats --top 20

Verify audit log integrity

python3 aicore.py --guardian-model guardian_model.json audit-verify


---

Marketplace (Renting “AI Nodes”)

The marketplace models a “GPU renting” system:

Spot market via an orderbook (bids)

Reserved contracts at fixed terms

Credits metering: renters pay credits for service units consumed by screening activity

Rewards can flow from block payouts into renter balances (depending on active reserved/spot winners)


Create a renter (generates an API key)

python3 aicore.py --guardian-model guardian_model.json renter-create --renter alice

You’ll receive:

api_key (store it safely)

A hashed API record is stored in the sealed market state


Check renter status

python3 aicore.py --guardian-model guardian_model.json renter-status --renter alice --api-key <KEY>

Place a spot order (bid)

bid_bps is the renter’s requested share (in basis points: 0..10000) of the “renters pool”.

python3 aicore.py --guardian-model guardian_model.json order-place \
  --renter alice --api-key <KEY> --tier Gold --bid-bps 7000 --max-credits 3000

Create a reserved contract

Reserved contracts also grant credits (metering budget).

python3 aicore.py --guardian-model guardian_model.json reserved-create \
  --renter alice --api-key <KEY> --tier Gold --renters-pool-bps 6500 --duration-sec 3600 --credits 5000


---

Local Web UI

The Web UI is a local control panel + project documentation served only from localhost.

Start it with:

python3 aicore.py --guardian-model guardian_model.json node --web

Open:

http://127.0.0.1:8787


UI features:

project overview + architecture notes

buttons for Status, Init, Mine, and Audit verify

send transaction form

marketplace actions:

create renter

renter status

spot order place

reserved contract create




---

Security Model (Medium Security)

This prototype includes practical “anti-hack” safeguards:

API keys per renter stored as salted PBKDF2 hash (never stored in plaintext)

Signed marketplace actions (HMAC) with:

timestamp

nonce

signature over payload hash


Anti-replay: nonces rejected within a TTL window

Market state integrity: sealed file includes an HMAC MAC; tampering is detected

Optional encryption at rest: Fernet (if cryptography installed)

Audit log hash-chain (audit_log.jsonl): detects log removal or editing



---

Privacy (Medium)

Rejected/quarantined transactions return a privacy receipt:

Commitment hash

Proof placeholder (stub)


This avoids exposing detailed reasons publicly.
In reveal_to_sender mode, the sender receives private hints (still not public).


---

Configuration Notes

Common flags:

--datadir ./aichain_data

--threshold 0.7

--privacy-mode receipt_only | reveal_to_sender

--fleet-size 100000 (reduce for dev machines if needed)

--committee-size 21

--market-state ./market_secure_state.bin

--secret-file ./market_secret.key

--audit-log ./audit_log.jsonl


Example:

python3 aicore.py --guardian-model guardian_model.json --fleet-size 5000 --committee-size 11 node --web


---

Roadmap (Next Practical Steps)

Replace privacy receipt stub with real ZK proof system

True P2P networking + peer discovery

Real RPC interface (auth + local-only)

Better mempool policies + fee market

Smarter orderbook allocation (top-N splitting, fair scheduling)

More robust key management (hardware-backed options)



---

License

Choose your license (MIT/Apache-2.0/GPLv3).
This repository is a prototype; you should audit and harden before any real deployment.
