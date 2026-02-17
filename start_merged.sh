#!/data/data/com.termux/files/usr/bin/bash
set -e

cd ~/RamIA

echo "[1/2] Starting RamIA Policy Service..."
python3 ramia_policy_service.py --host 127.0.0.1 --port 8787 &
POLICY_PID=$!

sleep 1
echo "[policy] PID=$POLICY_PID"
echo "[policy] health:"
python3 - <<'PY'
import urllib.request, json
print(json.loads(urllib.request.urlopen("http://127.0.0.1:8787/health").read()))
PY

echo ""
echo "[2/2] QuantumCore is under vendor/quantumcore"
echo "Set RAMIA_POLICY_URL=http://127.0.0.1:8787 in your environment"
echo ""
echo "Next: go to your QuantumCore desktop folder and run it:"
echo "  cd vendor/quantumcore/QuantumCore_ENV_Runtime_Patch/desktop"
echo "  npm install"
echo "  RAMIA_POLICY_URL=http://127.0.0.1:8787 npm run dev   (or npm start)"
echo ""
echo "To stop policy service:"
echo "  kill $POLICY_PID"
