#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

# Prevent sleep (best effort)
if command -v termux-wake-lock >/dev/null 2>&1; then
  termux-wake-lock || true
fi

LOGDIR="./logs"
mkdir -p "$LOGDIR"

MINER="${1:-miner_1}"
DATADIR="${RAMIA_DATADIR:-./aichain_data}"

echo "[run_node] miner=$MINER datadir=$DATADIR"
echo "[run_node] logs in $LOGDIR"
echo

while true; do
  TS="$(date +%Y%m%d-%H%M%S)"
  echo "[run_node] starting mine loop at $TS" | tee -a "$LOGDIR/supervisor.log"

  # 1) init (idempotent-ish)
  python3 aichain.py --datadir "$DATADIR" init >> "$LOGDIR/init.log" 2>&1 || true

  # 2) mine ONE attempt (your aichain mine may run long; we log it)
  python3 ramia_node.py mine "$MINER" >> "$LOGDIR/mine.log" 2>&1 || true

  # 3) verify reward ledger (won't fail if missing)
  python3 ramia_rewards_ledger.py >> "$LOGDIR/ledger_verify.log" 2>&1 || true

  echo "[run_node] cycle complete. sleeping 2s..." | tee -a "$LOGDIR/supervisor.log"
  sleep 2
done
