#!/usr/bin/env python3
# ramia_update_satoshi.py
# 목적: Generate 3 auditable files (node wrapper, local AI guardian, config)
# and optionally patch aichain.py with a minimal policy hook.
#
# Philosophy: default mode DOES NOT modify existing core files.
# Everything is deterministic, explicit, reversible (backups).

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

ROOT = Path(__file__).resolve().parent

NODE_PY = ROOT / "ramia_node.py"
AI_PY   = ROOT / "ramia_ai_guardian.py"
CFG_JS  = ROOT / "ramia_config.json"

AICHAIN = ROOT / "aichain.py"


# -----------------------------
# Helpers (safe, auditable)
# -----------------------------
def die(msg: str, code: int = 1) -> None:
    print(f"[fatal] {msg}", file=sys.stderr)
    raise SystemExit(code)

def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def write_text_atomic(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)

def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))

def ensure_repo_root() -> None:
    if not (ROOT / ".git").exists():
        # not fatal, but warn
        print("[warn] .git not found here. Are you in the repo root?")
    if not AICHAIN.exists():
        print("[warn] aichain.py not found in this folder. Wrapper will still be generated.")


# -----------------------------
# Templates (the 3 files)
# -----------------------------
def template_config() -> Dict[str, Any]:
    # Keep it small & explicit. Deterministic defaults.
    return {
        "node": {
            "name": "ramia-termux-node",
            "datadir": "./aichain_data",
            "network": "local-dev",
        },
        "ai_guardian": {
            "mode": "warn",              # "warn" | "fee_multiplier" | "reject"
            "threshold": 0.75,           # risk >= threshold triggers action
            "fee_multiplier": 2.0,       # only used if mode == "fee_multiplier"
            "reason_codes": True,
        },
        "rewards": {
            "enabled": True,
            "rule": "deterministic",     # deterministic-only for auditability
            "base_reward": 1.0,
            "risk_penalty": 0.5,         # reward * (1 - risk*risk_penalty)
        },
        "security": {
            "require_local_only": True,  # default: bind services to 127.0.0.1
            "allow_unsigned_dev_tx": True,
        }
    }

def template_ai_py() -> str:
    return r'''#!/usr/bin/env python3
# ramia_ai_guardian.py
# Local AI "Guardian" — deterministic, auditable scoring.
#
# This is NOT a magical ML oracle. It is a deterministic risk scorer
# designed for reproducible experiments and simple policy hooks.

from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Tuple, List

# -----------------------------
# Deterministic "features"
# -----------------------------
def _h(s: str) -> int:
    return int(hashlib.sha256(s.encode("utf-8")).hexdigest(), 16)

@dataclass(frozen=True)
class Decision:
    risk: float
    action: str  # "allow" | "warn" | "fee_multiplier" | "reject"
    reasons: List[str]

def score_tx(tx: Dict[str, Any]) -> Tuple[float, List[str]]:
    """
    Compute a deterministic risk score in [0,1].
    Inputs expected (best-effort):
      - txid/hash, from, to, amount, timestamp, fee, memo/data
    Missing fields are handled safely.
    """
    reasons: List[str] = []

    txid = str(tx.get("txid") or tx.get("hash") or "")
    sender = str(tx.get("from") or tx.get("sender") or "")
    to = str(tx.get("to") or tx.get("recipient") or "")
    amount = tx.get("amount") or tx.get("value") or 0
    fee = tx.get("fee") or 0
    memo = str(tx.get("memo") or tx.get("data") or "")

    # Feature 1: tiny-fee / zero-fee spam tendency
    fee_float = float(fee) if _is_number(fee) else 0.0
    if fee_float <= 0:
        reasons.append("fee<=0")

    # Feature 2: suspicious memo length (very long payloads)
    if len(memo) > 256:
        reasons.append("memo>256")

    # Feature 3: amount anomalies (negative/NaN)
    amt_float = float(amount) if _is_number(amount) else 0.0
    if amt_float < 0:
        reasons.append("amount<0")

    # Feature 4: hash entropy proxy (purely deterministic)
    # Not "security", just a stable signal for tests.
    blob = f"{txid}|{sender}|{to}|{amount}|{fee}|{memo}"
    x = _h(blob)
    # Map hash to [0,1]
    base = (x % 10_000) / 10_000.0

    # Combine: base + penalties, clipped to [0,1]
    risk = base
    if "fee<=0" in reasons:
        risk = min(1.0, risk + 0.20)
    if "memo>256" in reasons:
        risk = min(1.0, risk + 0.20)
    if "amount<0" in reasons:
        risk = 1.0

    return float(risk), reasons

def decide(tx: Dict[str, Any], cfg: Dict[str, Any]) -> Decision:
    ai = cfg.get("ai_guardian", {})
    mode = str(ai.get("mode", "warn"))
    threshold = float(ai.get("threshold", 0.75))

    risk, reasons = score_tx(tx)

    if risk < threshold:
        return Decision(risk=risk, action="allow", reasons=reasons)

    # Above threshold => enforce configured policy
    if mode == "reject":
        return Decision(risk=risk, action="reject", reasons=reasons)
    if mode == "fee_multiplier":
        return Decision(risk=risk, action="fee_multiplier", reasons=reasons)
    # default "warn"
    return Decision(risk=risk, action="warn", reasons=reasons)

def reward_for_work(work_units: float, risk: float, cfg: Dict[str, Any]) -> float:
    """
    Deterministic reward: base_reward*work_units * (1 - risk*risk_penalty).
    """
    r = cfg.get("rewards", {})
    base = float(r.get("base_reward", 1.0))
    pen = float(r.get("risk_penalty", 0.5))
    reward = base * float(work_units) * max(0.0, 1.0 - (risk * pen))
    return float(reward)

def _is_number(x: Any) -> bool:
    try:
        float(x)
        return True
    except Exception:
        return False
'''

def template_node_py() -> str:
    return r'''#!/usr/bin/env python3
# ramia_node.py
# Terminal-first "node wrapper" that integrates local AI Guardian WITHOUT
# modifying core files by default. Easy to audit.
#
# Commands:
#   init, mine, chain, send, score, reward
#
# This wrapper assumes your existing aichain.py CLI exists.
# If not, it still provides score/reward utilities.

from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent
CFG_PATH = ROOT / "ramia_config.json"

def load_cfg() -> Dict[str, Any]:
    if not CFG_PATH.exists():
        print("[fatal] ramia_config.json not found. Run: python3 ramia_update_satoshi.py --generate", file=sys.stderr)
        raise SystemExit(1)
    return json.loads(CFG_PATH.read_text(encoding="utf-8"))

def run_aichain(args: list[str]) -> int:
    aichain = ROOT / "aichain.py"
    if not aichain.exists():
        print("[fatal] aichain.py not found in repo root.", file=sys.stderr)
        return 2
    cmd = [sys.executable, str(aichain)] + args
    return subprocess.call(cmd)

def cmd_init(cfg: Dict[str, Any]) -> int:
    datadir = cfg["node"]["datadir"]
    return run_aichain(["--datadir", datadir, "init"])

def cmd_mine(cfg: Dict[str, Any], miner: str) -> int:
    datadir = cfg["node"]["datadir"]
    return run_aichain(["--datadir", datadir, "mine", miner])

def cmd_chain(cfg: Dict[str, Any], n: int) -> int:
    datadir = cfg["node"]["datadir"]
    return run_aichain(["--datadir", datadir, "chain", "--n", str(n)])

def cmd_send(cfg: Dict[str, Any], sender: str, to: str, amount: str, fee: str, memo: str) -> int:
    # Build tx payload for AI scoring (best-effort).
    tx = {"from": sender, "to": to, "amount": amount, "fee": fee, "memo": memo}

    from ramia_ai_guardian import decide
    d = decide(tx, cfg)
    print(f"[guardian] risk={d.risk:.4f} action={d.action} reasons={d.reasons}")

    if d.action == "reject":
        print("[guardian] rejected tx by policy.")
        return 3

    # If fee_multiplier, scale fee deterministically.
    if d.action == "fee_multiplier":
        mult = float(cfg.get("ai_guardian", {}).get("fee_multiplier", 2.0))
        try:
            f = float(fee)
            fee = str(f * mult)
            print(f"[guardian] fee scaled to {fee} (x{mult})")
        except Exception:
            pass

    # Delegate to aichain.py send interface (adjust if your CLI differs)
    # Many variants exist; keep explicit, you can tweak arguments here.
    datadir = cfg["node"]["datadir"]
    args = ["--datadir", datadir, "send", sender, to, str(amount)]
    # If your aichain.py supports fee/memo flags, add them:
    # args += ["--fee", str(fee), "--memo", memo]
    return run_aichain(args)

def cmd_score(cfg: Dict[str, Any], tx_json: str) -> int:
    from ramia_ai_guardian import decide
    tx = json.loads(tx_json)
    d = decide(tx, cfg)
    print(json.dumps({"risk": d.risk, "action": d.action, "reasons": d.reasons}, indent=2))
    return 0

def cmd_reward(cfg: Dict[str, Any], work_units: float, tx_json: str) -> int:
    from ramia_ai_guardian import decide, reward_for_work
    tx = json.loads(tx_json)
    d = decide(tx, cfg)
    rew = reward_for_work(work_units, d.risk, cfg)
    print(json.dumps({"work_units": work_units, "risk": d.risk, "reward": rew}, indent=2))
    return 0

def main() -> int:
    cfg = load_cfg()

    p = argparse.ArgumentParser(prog="ramia_node.py", description="RamIA terminal node wrapper (AI-guarded).")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")
    m = sub.add_parser("mine"); m.add_argument("miner")
    c = sub.add_parser("chain"); c.add_argument("--n", type=int, default=10)
    s = sub.add_parser("send")
    s.add_argument("sender"); s.add_argument("to"); s.add_argument("amount")
    s.add_argument("--fee", default="0"); s.add_argument("--memo", default="")

    sc = sub.add_parser("score"); sc.add_argument("tx_json", help='JSON string, e.g. \'{"from":"a","to":"b","amount":1}\'')
    rw = sub.add_parser("reward"); rw.add_argument("work_units", type=float); rw.add_argument("tx_json")

    a = p.parse_args()

    if a.cmd == "init":
        return cmd_init(cfg)
    if a.cmd == "mine":
        return cmd_mine(cfg, a.miner)
    if a.cmd == "chain":
        return cmd_chain(cfg, a.n)
    if a.cmd == "send":
        return cmd_send(cfg, a.sender, a.to, a.amount, a.fee, a.memo)
    if a.cmd == "score":
        return cmd_score(cfg, a.tx_json)
    if a.cmd == "reward":
        return cmd_reward(cfg, a.work_units, a.tx_json)

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
'''


# -----------------------------
# Optional patching of aichain.py
# -----------------------------
PATCH_MARKER_START = "# >>> RAMIA_GUARDIAN_HOOK_START"
PATCH_MARKER_END   = "# <<< RAMIA_GUARDIAN_HOOK_END"

def patch_aichain() -> Tuple[bool, str]:
    """
    Minimal patch: add an optional import + helper that can be manually used.
    We do NOT attempt to rewrite CLI. This is intentionally conservative.
    """
    if not AICHAIN.exists():
        return False, "aichain.py not found; skipping patch."

    src = AICHAIN.read_text(encoding="utf-8")
    if PATCH_MARKER_START in src:
        return True, "aichain.py already patched."

    backup = AICHAIN.with_suffix(".py.bak")
    shutil.copy2(AICHAIN, backup)

    hook = f"""
{PATCH_MARKER_START}
# Minimal, auditable policy hook (optional use).
# This does not change behavior unless you call ramia_guardian_decide(tx_dict).
try:
    from ramia_ai_guardian import decide as ramia_guardian_decide
except Exception:
    ramia_guardian_decide = None
{PATCH_MARKER_END}
"""

    # Insert near top after imports (very conservative)
    lines = src.splitlines()
    insert_at = 0
    for i, line in enumerate(lines[:80]):
        if line.strip().startswith("import ") or line.strip().startswith("from "):
            insert_at = i + 1

    lines.insert(insert_at, hook.strip("\n"))
    new_src = "\n".join(lines) + "\n"
    write_text_atomic(AICHAIN, new_src)

    return True, f"Patched aichain.py (backup: {backup.name})."


# -----------------------------
# Main generator
# -----------------------------
def generate_files() -> None:
    ensure_repo_root()

    cfg = template_config()
    write_text_atomic(CFG_JS, json.dumps(cfg, indent=2) + "\n")
    write_text_atomic(AI_PY, template_ai_py())
    write_text_atomic(NODE_PY, template_node_py())

    # Make scripts executable on unix-like systems (Termux)
    try:
        os.chmod(AI_PY, 0o755)
        os.chmod(NODE_PY, 0o755)
    except Exception:
        pass

    print("[ok] Generated:")
    print(f"  - {CFG_JS.name}")
    print(f"  - {AI_PY.name}")
    print(f"  - {NODE_PY.name}")

    if AICHAIN.exists():
        print(f"[info] aichain.py sha256: {sha256_file(AICHAIN)}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate RamIA Satoshi-style node+AI+config (auditable).")
    ap.add_argument("--generate", action="store_true", help="Generate 3 files (default action).")
    ap.add_argument("--patch", action="store_true", help="Optionally patch aichain.py with a minimal hook (creates .bak).")
    args = ap.parse_args()

    do_generate = args.generate or (not args.patch)
    if do_generate:
        generate_files()

    if args.patch:
        ok, msg = patch_aichain()
        print("[ok]" if ok else "[warn]", msg)

    print("\nNext:")
    print("  python3 ramia_node.py init")
    print("  python3 ramia_node.py mine miner_1")
    print("  python3 ramia_node.py chain --n 10")
    print("  python3 ramia_node.py score '{\"from\":\"a\",\"to\":\"b\",\"amount\":1,\"fee\":0}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
