#!/data/data/com.termux/files/usr/bin/bash
set -e

pkg update -y && pkg upgrade -y
pkg install -y python git

python -m pip install --upgrade pip

echo "Termux dependencies installed."
echo "Next: run ./scripts/termux_run.sh"
