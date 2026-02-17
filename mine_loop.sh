cd ~/RamIA
cat > mine_loop.sh <<'SH'
#!/data/data/com.termux/files/usr/bin/bash
set -e

# Keep CPU awake (best-effort)
termux-wake-lock >/dev/null 2>&1 || true

cd ~/RamIA
mkdir -p logs

WALLET_PUB="${WALLET_PUB:-wallet_public.json}"
DATADIR="${DATADIR:-./aichain_data}"
ENGINE="${ENGINE:-aichain_ai.py}"

# 1) Ensure wallet_public.json exists
if [ ! -f "$WALLET_PUB" ]; then
  echo "[miner] $WALLET_PUB not found."
  echo "[miner] Create it with:"
  echo "  python3 ramia_wallet_secure.py export-pub --wallet wallet.secure.json --out wallet_public.json"
  exit 2
fi

# 2) Extract primary address from wallet_public.json (supports several formats)
ADDR="$(python3 - <<'PY'
import json, sys
p="wallet_public.json"
d=json.load(open(p,"r",encoding="utf-8"))

# common direct fields
for k in ("address","addr","primary_address","receive_address","default_address"):
    v=d.get(k)
    if isinstance(v,str) and v.strip():
        print(v.strip()); sys.exit(0)

# list candidates
for k in ("addresses","addrs","receive","accounts","wallets"):
    v=d.get(k)
    if isinstance(v,list) and v:
        first=v[0]
        if isinstance(first,str) and first.strip():
            print(first.strip()); sys.exit(0)
        if isinstance(first,dict):
            for kk in ("address","addr","receive","default"):
                vv=first.get(kk)
                if isinstance(vv,str) and vv.strip():
                    print(vv.strip()); sys.exit(0)

# dict candidates nested
for k,v in d.items():
    if isinstance(v,dict):
        for kk in ("address","addr","receive_address"):
            vv=v.get(kk)
            if isinstance(vv,str) and vv.strip():
                print(vv.strip()); sys.exit(0)

print("NO_ADDRESS_FOUND")
sys.exit(1)
PY
)" || true

if [ "$ADDR" = "NO_ADDRESS_FOUND" ] || [ -z "$ADDR" ]; then
  echo "[miner] Could not find an address in $WALLET_PUB"
  echo "[miner] Run this to show structure (safe):"
  echo "  python3 - <<'PY'"
  echo "  import json; d=json.load(open('wallet_public.json'));"
  echo "  print('keys:', list(d.keys()));"
  echo "  PY"
  exit 3
fi

echo "[miner] Using address: $ADDR"
echo "[miner] Engine: $ENGINE"
echo "[miner] Datadir: $DATADIR"

# 3) Initialize chain if missing
if [ ! -d "$DATADIR" ]; then
  echo "[miner] Datadir not found, initializing..."
  python3 "$ENGINE" --datadir "$DATADIR" init | tee -a logs/miner.log
fi

# 4) Infinite mining loop with logs + auto-restart
while true; do
  echo "---- $(date) ----" | tee -a logs/miner.log
  python3 "$ENGINE" --datadir "$DATADIR" mine "$ADDR" 2>&1 | tee -a logs/miner.log
  sleep 1
done
SH

chmod +x mine_loop.sh
