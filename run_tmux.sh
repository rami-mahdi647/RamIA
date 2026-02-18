#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

pkg install -y tmux >/dev/null 2>&1 || true

SESSION="ramia"
MINER="${1:-miner_1}"

# Wake lock (best effort)
if command -v termux-wake-lock >/dev/null 2>&1; then
  termux-wake-lock || true
fi

# Create session if missing
if ! tmux has-session -t "$SESSION" 2>/dev/null; then
  tmux new-session -d -s "$SESSION" "cd ~/RamIA && ./run_node.sh $MINER"
  echo "[tmux] started session: $SESSION"
else
  echo "[tmux] session already running: $SESSION"
fi

echo
echo "Attach to see logs:"
echo "  tmux attach -t $SESSION"
echo
echo "Detach without stopping:"
echo "  Ctrl+B then D"
echo
echo "Stop everything:"
echo "  tmux kill-session -t $SESSION"
