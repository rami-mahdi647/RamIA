# INSTALL (CLI-Only)

RamIA now runs as a terminal-first blockchain/wallet project.

For complete cross-platform instructions (Termux, Kali, Ubuntu, macOS, Windows), use:
- `README.md`

Quick verification after clone:

```bash
python3 tokenomics_v1.py --self-test
python3 aichain.py --datadir ./aichain_data init
python3 aichain.py --datadir ./aichain_data mine miner_demo
python3 aichain.py --datadir ./aichain_data chain --n 5
```
