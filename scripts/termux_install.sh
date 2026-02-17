#!/data/data/com.termux/files/usr/bin/bash
set -e

pkg update -y && pkg upgrade -y
pkg install -y python git

python -m pip install --upgrade pip

# optional deps (ignore if fail)
# pkg install -y clang rust openssl libffi pkg-config || true
# pip install --no-build-isolation cryptography || true

if [ ! -f "dataset.csv" ]; then
  ./scripts/make_dataset_demo.sh
fi

python3 aiguardian.py train --csv dataset.csv --out guardian_model.json

if [ ! -f "ramia.conf" ]; then
  cp ./configs/ramia.conf.example ./ramia.conf
fi

echo "OK. Now run: ./scripts/termux_run.sh"
