# AIChain (prototype)

A minimal blockchain nucleus with two AI hooks:

1) **Dynamic issuance policy** (block subsidy never “ends”): a replaceable policy model computes subsidy from network metrics (miners/nodes/tx pressure/mempool).
2) **AIGuardian** (defensive filter): a lightweight ML scorer to flag spam/abuse patterns before mempool admission.

This repo is intentionally small and legible. It is not production software.

## Files

- `aichain.py` — chain + PoW + state + dynamic subsidy hook.
- `aiguardian.py` — training + scoring pipeline (pure python logistic regression).

## Quick start

```bash
python3 aichain.py --datadir ./data init
python3 aichain.py --datadir ./data balance genesis
python3 aichain.py --datadir ./data send genesis alice 100000 --fee 1000 --memo "hello"
python3 aichain.py --datadir ./data mine miner1
python3 aichain.py --datadir ./data chain --n 5
