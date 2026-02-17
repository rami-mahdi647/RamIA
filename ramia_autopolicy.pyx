#!/usr/bin/env python3
"""
ramia_autopolicy.py  (single-file tool)

GOAL (what this file does):
1) Fix insane issuance (e.g., 50,000,000 tokens per block) WITHOUT editing files manually:
   - Reads your existing aichain.py
   - Generates a new file aichain_ai.py with:
       - Supply-capped dynamic issuance (default total supply 100,000,000)
       - Congestion-aware subsidy adjustment (signals from public Bitcoin mempool/fees)

2) Optional: Run AI Guardian v2 (fee penalty + warnings) if present in repo.

This is terminal-first, developer-only.

Public signals:
- mempool.space REST API docs for mempool endpoints. https://mempool.space/docs/api/rest 3
- Blockstream explorer API. https://blockstream.info/explorer-api 4

USAGE (Termux/Linux/macOS/Windows):
  # A) Audit what your current aichain.py is doing
  python ramia_autopolicy.py audit-issuance --aichain aichain.py

  # B) Generate patched chain engine as a NEW file aichain_ai.py
  python ramia_autopolicy.py patch-issuance --aichain aichain.py --out aichain_ai.py --total-supply 100000000

  # C) Run the patched engine (same CLI as aichain.py)
  python aichain_ai.py --datadir ./aichain_data init
  python aichain_ai.py --datadir ./aichain_data mine miner_rami
  python aichain_ai.py --datadir ./aichain_data chain --n 10

  # D) (Optional) Run guarded bridge if model exists:
  python ramia_autopolicy.py run-guarded --model guardian_model.json --threshold 0.70 --mode fee-bump -- aichain_ai.py --datadir ./aichain_data node

NOTES:
- This file does NOT implement real cryptographic signatures; it fixes issuance + adds policy hooks.
- Supply cap is enforced at issuance calculation time. (No more "50M per block" when supply=100M.)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, List


# --------------------------
# Public signal fetch (stdlib)
# --------------------------

def _http_get_json(url: str, timeout: int = 10) -> Optional[Dict[str, Any]]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RamIA/1.0 (autopolicy)"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        return json.loads(data.decode("utf-8"))
    except Exception:
        return None


def fetch_btc_mempool_signals() -> Dict[str, Any]:
    """
    Try mempool.space first, then blockstream as fallback.
    Returns:
      mempool_txs (int)
      mempool_vbytes (int)
      fee_fast (float)  # sat/vB-like number if available
      fee_hour (float)
      fee_econ (float)
      source (str)
    """
    # mempool.space endpoints
    mp_mempool = _http_get_json("https://mempool.space/api/mempool")
    mp_fees = _http_get_json("https://mempool.space/api/v1/fees/recommended")

    if mp_mempool and mp_fees:
        return {
            "mempool_txs": int(mp_mempool.get("count", 0)),
            "mempool_vbytes": int(mp_mempool.get("vsize", 0)),
            "fee_fast": float(mp_fees.get("fastestFee", 0.0)),
            "fee_hour": float(mp_fees.get("hourFee", 0.0)),
            "fee_econ": float(mp_fees.get("economyFee", 0.0)),
            "source": "mempool.space",
        }

    # blockstream fallback (fee-estimates is map: target_blocks -> feerate)
    bs_fees = _http_get_json("https://blockstream.info/api/fee-estimates")
    # blockstream has mempool endpoint too, but formats differ across deployments; we keep it simple.
    if bs_fees:
        # choose typical targets if present
        fast = float(bs_fees.get("1", bs_fees.get("2", 0.0)) or 0.0)
        hour = float(bs_fees.get("6", bs_fees.get("10", 0.0)) or 0.0)
        econ = float(bs_fees.get("144", bs_fees.get("100", 0.0)) or 0.0)
        return {
            "mempool_txs": 0,
            "mempool_vbytes": 0,
            "fee_fast": fast,
            "fee_hour": hour,
            "fee_econ": econ,
            "source": "blockstream.info",
        }

    return {
        "mempool_txs": 0,
        "mempool_vbytes": 0,
        "fee_fast": 0.0,
        "fee_hour": 0.0,
        "fee_econ": 0.0,
        "source": "none",
    }


# --------------------------
# Issuance logic (supply-capped, congestion-aware)
# --------------------------

@dataclass
class IssuanceConfig:
    total_supply: int = 100_000_000           # total tokens in existence (cap)
    target_block_time_sec: int = 60           # your chain uses ~60 seconds
    target_years: int = 10                    # distribute over N years (dev default)
    min_subsidy: int = 1                      # never 0 (unless cap reached)
    max_subsidy: int = 5000                   # safety cap per block (dev default)


def compute_target_blocks(cfg: IssuanceConfig) -> int:
    secs = cfg.target_years * 365 * 24 * 3600
    return max(1, secs // max(1, cfg.target_block_time_sec))


def compute_dynamic_subsidy(
    height: int,
    already_issued: int,
    cfg: IssuanceConfig,
    signals: Dict[str, Any],
) -> int:
    """
    Supply-capped dynamic issuance:
    - remaining = total_supply - already_issued
    - baseline = remaining / remaining_blocks (smooth glidepath)
    - congestion multiplier from Bitcoin mempool/fees signals
    - clamp to [min_subsidy, max_subsidy], but never exceed remaining
    """
    remaining = cfg.total_supply - max(0, already_issued)
    if remaining <= 0:
        return 0

    target_blocks = compute_target_blocks(cfg)
    remaining_blocks = max(1, target_blocks - max(0, height))
    baseline = max(1, remaining // remaining_blocks)

    # Congestion / fee pressure: if BTC fees high, we slightly increase rewards
    # (incentivize more validation capacity) BUT bounded by max_subsidy.
    fee_fast = float(signals.get("fee_fast", 0.0))
    mempool_txs = int(signals.get("mempool_txs", 0))

    # Normalize (very rough; dev heuristic)
    fee_pressure = min(3.0, fee_fast / 50.0)          # 50 sat/vB ~ "busy"
    mempool_pressure = min(3.0, mempool_txs / 50_000) # 50k tx mempool ~ "busy"
    pressure = max(fee_pressure, mempool_pressure)

    # multiplier between 1.0 and 1.75
    mult = 1.0 + min(0.75, 0.25 * pressure)

    sub = int(baseline * mult)

    # Clamp
    sub = max(cfg.min_subsidy, min(cfg.max_subsidy, sub))
    sub = min(sub, remaining)
    return sub


# --------------------------
# Patch generator: create a NEW aichain_ai.py
# --------------------------

PATCH_BANNER = """# --- RamIA AutoPolicy Patch ---
# This file was generated by ramia_autopolicy.py
# Changes:
# - Replace fixed IssuancePolicy(base_subsidy=50_000_000, ...) with supply-capped dynamic issuance.
# - Pull optional public congestion signals (BTC mempool/fees) to modulate subsidy within safe bounds.
# - Keeps original CLI intact.
# --------------------------------
"""

def audit_issuance(aichain_path: str) -> Tuple[bool, str]:
    if not os.path.exists(aichain_path):
        return False, f"Missing file: {aichain_path}"
    txt = open(aichain_path, "r", encoding="utf-8", errors="replace").read()
    m = re.search(r"IssuancePolicy\(\s*[^)]*base_subsidy\s*=\s*([0-9_]+)", txt, flags=re.S)
    if not m:
        return False, "Could not find IssuancePolicy(base_subsidy=...) in aichain.py"
    base = m.group(1)
    return True, f"Found base_subsidy={base} (this is likely why you see ~50,000,000 per block)."


def patch_issuance(aichain_path: str, out_path: str, cfg: IssuanceConfig) -> Tuple[bool, str]:
    if not os.path.exists(aichain_path):
        return False, f"Missing file: {aichain_path}"
    src = open(aichain_path, "r", encoding="utf-8", errors="replace").read()

    # 1) Inject helper functions near the top (after imports)
    inject_code = f"""
{PATCH_BANNER}
import urllib.request as _ramia_urllib_request
import json as _ramia_json

def _ramia_http_get_json(url: str, timeout: int = 10):
    try:
        req = _ramia_urllib_request.Request(url, headers={{"User-Agent":"RamIA/1.0 (autopolicy)"}})
        with _ramia_urllib_request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        return _ramia_json.loads(data.decode("utf-8"))
    except Exception:
        return None

def _ramia_fetch_btc_signals():
    mp_mempool = _ramia_http_get_json("https://mempool.space/api/mempool")
    mp_fees = _ramia_http_get_json("https://mempool.space/api/v1/fees/recommended")
    if mp_mempool and mp_fees:
        return {{
            "mempool_txs": int(mp_mempool.get("count", 0)),
            "mempool_vbytes": int(mp_mempool.get("vsize", 0)),
            "fee_fast": float(mp_fees.get("fastestFee", 0.0)),
            "fee_hour": float(mp_fees.get("hourFee", 0.0)),
            "fee_econ": float(mp_fees.get("economyFee", 0.0)),
            "source": "mempool.space",
        }}
    bs_fees = _ramia_http_get_json("https://blockstream.info/api/fee-estimates")
    if bs_fees:
        fast = float(bs_fees.get("1", bs_fees.get("2", 0.0)) or 0.0)
        hour = float(bs_fees.get("6", bs_fees.get("10", 0.0)) or 0.0)
        econ = float(bs_fees.get("144", bs_fees.get("100", 0.0)) or 0.0)
        return {{
            "mempool_txs": 0,
            "mempool_vbytes": 0,
            "fee_fast": fast,
            "fee_hour": hour,
            "fee_econ": econ,
            "source": "blockstream.info",
        }}
    return {{"mempool_txs":0,"mempool_vbytes":0,"fee_fast":0.0,"fee_hour":0.0,"fee_econ":0.0,"source":"none"}}

_RAMIA_TOTAL_SUPPLY = {cfg.total_supply}
_RAMIA_TARGET_BLOCK_TIME = {cfg.target_block_time_sec}
_RAMIA_TARGET_YEARS = {cfg.target_years}
_RAMIA_MIN_SUBSIDY = {cfg.min_subsidy}
_RAMIA_MAX_SUBSIDY = {cfg.max_subsidy}

def _ramia_target_blocks():
    secs = _RAMIA_TARGET_YEARS * 365 * 24 * 3600
    return max(1, secs // max(1, _RAMIA_TARGET_BLOCK_TIME))

def _ramia_dynamic_subsidy(height: int, already_issued: int):
    remaining = _RAMIA_TOTAL_SUPPLY - max(0, already_issued)
    if remaining <= 0:
        return 0
    target_blocks = _ramia_target_blocks()
    remaining_blocks = max(1, target_blocks - max(0, height))
    baseline = max(1, remaining // remaining_blocks)

    sig = _ramia_fetch_btc_signals()
    fee_fast = float(sig.get("fee_fast", 0.0))
    mempool_txs = int(sig.get("mempool_txs", 0))

    fee_pressure = min(3.0, fee_fast / 50.0)
    mempool_pressure = min(3.0, mempool_txs / 50000.0)
    pressure = max(fee_pressure, mempool_pressure)

    mult = 1.0 + min(0.75, 0.25 * pressure)
    sub = int(baseline * mult)

    sub = max(_RAMIA_MIN_SUBSIDY, min(_RAMIA_MAX_SUBSIDY, sub))
    sub = min(sub, remaining)
    return sub
"""

    # Insert after the first block of imports (best-effort).
    # We inject right after the first blank line after imports.
    # If this fails, we put it at top.
    insert_pos = 0
    m = re.search(r"(\n\s*\n)", src)
    if m:
        insert_pos = m.end()

    patched = src[:insert_pos] + inject_code + src[insert_pos:]

    # 2) Patch IssuancePolicy.predict to use dynamic subsidy
    # We replace the whole predict body with a supply-capped call.
    # Keep signature same.
    predict_pat = r"(class\s+IssuancePolicy.*?\n\s+def\s+predict\s*\(.*?\)\s*:\n)(.*?)(\n\s+def\s+update|\n\s+@|\n\s+class|\n\s+def\s+)"
    pm = re.search(predict_pat, patched, flags=re.S)
    if not pm:
        return False, "Could not patch IssuancePolicy.predict (pattern mismatch)."

    head = pm.group(1)
    tail_marker = pm.group(3)

    # We need already_issued; ChainDB tracks blocks, so we approximate issued by summing coinbase outputs.
    # We'll add a helper on ChainDB later; here we accept parameters via fee_pressure inputs as before,
    # but we compute already_issued from 'self._issued' if present; otherwise 0 (then it will still clamp by max).
    new_predict_body = """
        # AutoPolicy: supply-capped dynamic issuance (dev)
        # We keep original signature but ignore learned weights for now.
        # 'fee_pressure' and other metrics are baked into BTC public signals.
        try:
            already_issued = int(getattr(self, "_issued", 0))
        except Exception:
            already_issued = 0
        # Height is not passed here, so we assume ChainDB sets self._height before calling.
        try:
            h = int(getattr(self, "_height", 0))
        except Exception:
            h = 0
        return _ramia_dynamic_subsidy(h, already_issued)
"""
    # rebuild patched predict region
    start = pm.start(1)
    end = pm.start(3)
    patched = patched[:start] + head + new_predict_body + patched[end:]

    # 3) Patch ChainDB to maintain _issued + _height on policy before calling predict
    # Find where policy.predict is called and set hints.
    # We do a simple replacement around "self.policy.predict(" occurrences.
    def _sum_coinbase_issued_code() -> str:
        return """
        # AutoPolicy: track total issued by summing coinbase outputs
        try:
            issued = 0
            for _b in self.blocks:
                try:
                    issued += sum(_o.amount for _o in _b.txs[0].vout)
                except Exception:
                    pass
            self.policy._issued = int(issued)
            self.policy._height = int(self.height())
        except Exception:
            pass
"""

    # Insert issued tracking into _make_block_template (or similar) by searching for policy.predict usage.
    if "self.policy.predict" not in patched:
        return False, "Could not find self.policy.predict call in ChainDB."

    patched = patched.replace("self.policy.predict(", _sum_coinbase_issued_code() + "\n        self.policy.predict(", 1)

    # 4) Patch the default IssuancePolicy instantiation to sane bounds (fallback if dynamic fails)
    # Replace base_subsidy=50_000_000 with base_subsidy=100
    patched = re.sub(
        r"base_subsidy\s*=\s*50_000_000",
        "base_subsidy=100",
        patched,
        count=1,
    )
    # Also clamp min/max a bit
    patched = re.sub(r"min_subsidy\s*=\s*1_000_000", f"min_subsidy={cfg.min_subsidy}", patched, count=1)
    patched = re.sub(r"max_subsidy\s*=\s*100_000_000", f"max_subsidy={cfg.max_subsidy}", patched, count=1)

    # Write new file
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(patched)
    return True, f"Wrote patched engine: {out_path} (run it like aichain.py)."


# --------------------------
# Guardian runner (optional)
# --------------------------

def run_guarded(model_path: str, threshold: float, mode: str, passthrough: List[str]) -> int:
    """
    Best-effort runner:
    - If aichain_guarded_v2.py exists, run it with your args and patches (fee penalty, warnings).
    - Otherwise, just run passthrough command.
    """
    guarded = "aichain_guarded_v2.py"
    if os.path.exists(guarded):
        cmd = [sys.executable, guarded, "--model", model_path, "--threshold", str(threshold), "--mode", mode, "--"] + passthrough
        return os.spawnv(os.P_WAIT, sys.executable, cmd)

    # Fallback: run command directly
    cmd = [sys.executable] + passthrough
    return os.spawnv(os.P_WAIT, sys.executable, cmd)


# --------------------------
# CLI
# --------------------------

def main() -> int:
    ap = argparse.ArgumentParser(prog="ramia_autopolicy.py", description="Generate aichain_ai.py (supply-capped dynamic issuance) + optional guardian runner.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("audit-issuance", help="Show current IssuancePolicy base_subsidy in aichain.py")
    a.add_argument("--aichain", default="aichain.py")
    a.set_defaults(_fn="audit")

    p = sub.add_parser("patch-issuance", help="Generate NEW aichain_ai.py with supply-capped dynamic issuance")
    p.add_argument("--aichain", default="aichain.py")
    p.add_argument("--out", default="aichain_ai.py")
    p.add_argument("--total-supply", type=int, default=100_000_000)
    p.add_argument("--target-years", type=int, default=10)
    p.add_argument("--block-time", type=int, default=60)
    p.add_argument("--min-subsidy", type=int, default=1)
    p.add_argument("--max-subsidy", type=int, default=5000)
    p.set_defaults(_fn="patch")

    g = sub.add_parser("run-guarded", help="Run guarded bridge if present (fee penalties + warnings)")
    g.add_argument("--model", required=True, help="guardian_model.json path")
    g.add_argument("--threshold", type=float, default=0.70)
    g.add_argument("--mode", default="fee-bump", choices=["deny", "quarantine", "fee-bump", "tag-only"])
    g.add_argument("sep", nargs="?", help="Use -- then the command to run")
    g.add_argument("cmdline", nargs=argparse.REMAINDER, help="Command to run, e.g. aichain_ai.py --datadir ...")
    g.set_defaults(_fn="guarded")

    args = ap.parse_args()

    if args._fn == "audit":
        ok, msg = audit_issuance(args.aichain)
        print(("ok" if ok else "error"), msg)
        return 0 if ok else 2

    if args._fn == "patch":
        cfg = IssuanceConfig(
            total_supply=args.total_supply,
            target_block_time_sec=args.block_time,
            target_years=args.target_years,
            min_subsidy=args.min_subsidy,
            max_subsidy=args.max_subsidy,
        )
        ok, msg = patch_issuance(args.aichain, args.out, cfg)
        print(("ok" if ok else "error"), msg)
        if ok:
            sig = fetch_btc_mempool_signals()
            print("public_signals_source", sig.get("source"))
            print("tip", "Run:", f"python {args.out} --datadir ./aichain_data init")
        return 0 if ok else 2

    if args._fn == "guarded":
        if not args.cmdline:
            print("error missing passthrough command. Example:")
            print("  python ramia_autopolicy.py run-guarded --model guardian_model.json --threshold 0.7 --mode fee-bump -- aichain_ai.py --datadir ./aichain_data node")
            return 2
        # drop a leading "--" if present
        cmdline = args.cmdline
        if cmdline and cmdline[0] == "--":
            cmdline = cmdline[1:]
        return int(run_guarded(args.model, args.threshold, args.mode, cmdline))

    return 0


if __name__ == "__main__":
    raise SystemExit(main()

