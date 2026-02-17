#!/data/data/com.termux/files/usr/bin/bash
set -e

python tokenomics_v1.py --self-test
python aichain.py --datadir ./aichain_data init
python aichain.py --datadir ./aichain_data mine miner_termux
python aichain.py --datadir ./aichain_data chain --n 5
