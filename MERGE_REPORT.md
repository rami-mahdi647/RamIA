# RamIA ⨉ QuantumCore — Merge Report
- Generated: Tue Feb 17 08:09:06 2026
- QuantumCore ZIP: `quantumcore-main (1).zip`
- QuantumCore extracted to: `vendor/quantumcore/`
- Policy layer: `vendor/ramia_policy/policy_layer.py`
- Runner: `run_merged_node.py`

## What got merged
### Copied from RamIA into vendor/ramia_policy/
- `aiguardian.py`
- `aichain_ai.py`
- `ramia_autopolicy.py`
- `ramia_wallet_secure.py`

## QuantumCore candidate entrypoints (auto-detected)
- None detected (you must specify --qc-entry)

## How to run (developer)
1) Install deps (if needed)
```bash
python --version
```
2) Try running QuantumCore through the runner
```bash
python run_merged_node.py --qc-entry vendor/quantumcore/<entrypoint>.py -- --help
```
3) Policy API available as RAMIA_POLICY
- tx_policy(tx_dict) -> ok, fee_mult, reasons, suggestions
- block_reward(metrics_dict) -> reward_int

## Next step (real production integration)
To fully integrate into QuantumCore production paths, connect policy hooks into:
- mempool acceptance (pre-check): apply tx_policy and fee penalties
- block template / coinbase: use block_reward for subsidy
- telemetry: feed active_nodes/miners/mempool/fees into metrics
