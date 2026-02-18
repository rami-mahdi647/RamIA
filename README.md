# RamIA — Terminal-First Blockchain Node (AI-Guarded) + Auditable Rewards (Medium-Security)

RamIA is a developer-first blockchain prototype built to run entirely from the terminal (Termux/Linux/macOS).  
It wraps a minimal chain engine (`aichain.py`) with an **AI Guardian** safety layer and an **append-only, hash-chained rewards ledger** designed for **medium-security auditing**.

> Goal: Make it easy for early adopters (developers) to run a node, mine, send transactions, and audit reward issuance—without hosting, dashboards, or hidden complexity.

---

## Repository Layout (Key Files)

- **`aichain.py`**  
  Core chain engine (block/tx/state). Kept as close to “core” as possible for auditability.

- **`ramia_node.py`**  
  Terminal node wrapper. Provides a clean CLI (`init`, `mine`, `send`, `chain`, etc.) and integrates the AI Guardian.  
  Includes a convenience conversion layer for fees (float input → integer units) to match `aichain.py` expectations.

- **`ramia_ai_guardian.py`**  
  Deterministic decision engine for risk scoring and policy actions (e.g., allow/warn/reject, fee scaling).

- **`ramia_rewards_ledger.py`**  
  Append-only rewards ledger (`.jsonl`) with **hash chaining** (`prev_hash` → `entry_hash`) to make edits tamper-evident.

- **`ramia_reward_policy.py`**  
  Deterministic reward function (tokenomics) driven by config. Bounded outputs (caps/floors) and explicit factors.

- **`ramia_config.json`**  
  Single source of truth for runtime config, tokenomics, and network metrics (until P2P discovery exists).

- **`run_node.sh` / `run_tmux.sh`**  
  Terminal-first “ops” scripts: persistent execution via `tmux`, restart loops, and file-based logs.

---

## Requirements

### Termux (Android)
```bash
pkg update -y
pkg install -y python git tmux

Linux (Debian/Ubuntu)

sudo apt-get update
sudo apt-get install -y python3 git tmux

> Python 3.10+ recommended (Termux may ship newer).




---

Quickstart

1) Clone

git clone git@github.com:rami-mahdi647/RamIA.git
cd RamIA

2) Initialize chain data

python3 ramia_node.py init

3) Start persistent mining (survives disconnect)

./run_tmux.sh miner_1

Attach:

tmux attach -t ramia

Detach (keep running):

Ctrl+B, then D


Stop:

tmux kill-session -t ramia


---

CLI Usage (ramia_node.py)

Show help:

python3 ramia_node.py -h

Mine

python3 ramia_node.py mine miner_1

View chain (last N blocks)

python3 ramia_node.py chain --n 10

Send a transaction (AI-guarded)

python3 ramia_node.py send alice bob 10 --fee 0.01 --memo "hello"

Fee model note

aichain.py expects --fee as an integer.
ramia_node.py accepts float-style fees (e.g. 0.01) and converts them into integer units using:

ramia_config.json → node.fee_unit


Example:

fee_unit = 0.01

--fee 0.01 → fee_int = 1

--fee 0.10 → fee_int = 10



---

Balances (core chain)

python3 aichain.py balance <ADDRESS>

If you use an explicit data directory:

python3 aichain.py --datadir ./aichain_data balance <ADDRESS>

> Important: Your private key does not store tokens. Tokens live in chain state; the private key only authorizes spending.




---

Logs

If you use run_node.sh / run_tmux.sh, logs are written under ./logs/.

Common:

logs/supervisor.log

logs/mine.log

logs/init.log

logs/ledger_verify.log


Tail mining output:

tail -f logs/mine.log


---

Auditable Rewards (Medium Security)

Rewards are recorded in:

aichain_data/rewards_ledger.jsonl


Each record includes:

prev_hash and entry_hash → tamper-evident chaining

an event with a reward breakdown for audit


Verify ledger integrity:

python3 ramia_rewards_ledger.py

Reward policy inputs (v0)

The policy is deterministic and config-driven. It currently supports factors like:

difficulty (via config estimate until P2P sync exists)

latency (placeholder until network instrumentation exists)

active nodes (explicit estimate until peer discovery exists)

AI risk score

work units


Configuration:

ramia_config.json → tokenomics, network_metrics


Policy code:

ramia_reward_policy.py


> Current design keeps reward logic out of the chain core to keep iteration fast and audits simple.
You can later migrate rewards into on-chain minting once consensus rules stabilize.




---

Tokenomics (v0)

Target max supply: 100,000,000

Deterministic reward outputs

Hard caps per event to prevent runaway issuance

Explicit config parameters for transparency


Key config fields:

tokenomics.max_supply

tokenomics.base_block_reward

tokenomics.max_reward_per_event

tokenomics.risk_penalty

network_metrics.active_nodes_estimate

network_metrics.difficulty_estimate



---

Mining Time (Expected)

Mining time depends heavily on:

PoW difficulty in aichain.py

your device’s compute power


For developer experience:

Devnet target: ~10–30s per block

Small network target: ~30–120s per block


If blocks take many minutes/hours on mobile, lower difficulty or add difficulty retargeting.


---

Security Notes (Medium-Security Baseline)

Reward ledger is tamper-evident via hash chaining (auditable offline).

Reward policy is deterministic and bounded.

Runtime artifacts (logs, chain data) should not be committed to Git.


Recommended .gitignore:

aichain_data/

logs/*.log

__pycache__/



---

Roadmap / Next Steps

1. Read difficulty from chain state automatically (remove config estimates)


2. P2P peer discovery + block sync


3. Optional: sign ledger entries per node (Ed25519)


4. Optional: migrate reward issuance to on-chain rules once stable




---

Contributing

Keep changes small and easy to review.

Prefer deterministic logic over dynamic heuristics.

Avoid introducing heavyweight dependencies.

Always update docs when adding commands or flags.



---

License

(TODO: add license)
