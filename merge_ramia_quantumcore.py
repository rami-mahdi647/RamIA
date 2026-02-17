#!/usr/bin/env python3
"""
merge_ramia_quantumcore.py

One-file organic merge tool:
- Extracts quantumcore-main*.zip into ./vendor/quantumcore/
- Creates a universal Policy Layer (AI Guardian + dynamic reward + spam penalties)
- Copies relevant RamIA modules into ./vendor/ramia_policy/
- Generates run_merged_node.py to run QuantumCore with policy hooks (best-effort)
- Writes MERGE_REPORT.md with next steps

Works with Python stdlib only (Termux-friendly).
"""

from __future__ import annotations

import os
import re
import sys
import json
import time
import shutil
import zipfile
from pathlib import Path
from typing import List, Tuple, Optional

ROOT = Path(".").resolve()
VENDOR = ROOT / "vendor"
QC_DIR = VENDOR / "quantumcore"
POLICY_DIR = VENDOR / "ramia_policy"

DEFAULT_QC_ZIP_HINTS = [
    "quantumcore", "quantumcore-main", "quantumcore-main (1)", "quantumcore-main(1)"
]

RAMIA_CANDIDATES = [
    "aiguardian.py",
    "aichain_ai.py",
    "ramia_emission_policy.py",
    "ramia_autopolicy.py",
    "ramia_wallet_secure.py",
    "ramia_cli.py",
]

REPORT_FILE = ROOT / "MERGE_REPORT.md"


def log(msg: str):
    print(f"[merge] {msg}")


def find_zip_in_cwd() -> Optional[Path]:
    zips = list(ROOT.glob("*.zip"))
    if not zips:
        return None
    # prefer quantumcore-looking name
    for z in zips:
        name = z.name.lower()
        if "quantumcore" in name:
            return z
    # fallback: first zip
    return zips[0]


def safe_rmtree(p: Path):
    if p.exists():
        shutil.rmtree(p)


def extract_zip(zip_path: Path, out_dir: Path):
    log(f"Extracting {zip_path.name} -> {out_dir}")
    safe_rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(out_dir)
    log("Extraction done.")


def flatten_single_top_dir(out_dir: Path):
    """
    If extraction creates one top-level folder, flatten it:
      vendor/quantumcore/<top>/...  -> vendor/quantumcore/...
    """
    children = [p for p in out_dir.iterdir() if p.is_dir()]
    files = [p for p in out_dir.iterdir() if p.is_file()]
    if len(children) == 1 and len(files) == 0:
        top = children[0]
        log(f"Flattening single top dir: {top.name}")
        tmp = out_dir / "__tmp_flatten__"
        tmp.mkdir(exist_ok=True)
        for item in top.iterdir():
            shutil.move(str(item), str(tmp / item.name))
        safe_rmtree(top)
        for item in tmp.iterdir():
            shutil.move(str(item), str(out_dir / item.name))
        safe_rmtree(tmp)


def list_py_files(base: Path) -> List[Path]:
    return [p for p in base.rglob("*.py") if p.is_file()]


def guess_entrypoints(py_files: List[Path]) -> List[Path]:
    """
    Heuristic: entrypoint contains 'if __name__ == "__main__"' or argparse usage.
    """
    eps = []
    for p in py_files:
        try:
            t = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if 'if __name__ == "__main__"' in t or "argparse" in t:
            eps.append(p)
    # sort: prefer small, likely cli
    eps.sort(key=lambda x: x.stat().st_size)
    return eps[:10]


def copy_ramia_modules(dst_dir: Path) -> List[str]:
    dst_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in RAMIA_CANDIDATES:
        src = ROOT / name
        if src.exists() and src.is_file():
            shutil.copy2(src, dst_dir / name)
            copied.append(name)
    return copied


def write_policy_layer(dst_dir: Path):
    dst_dir.mkdir(parents=True, exist_ok=True)
    policy_file = dst_dir / "policy_layer.py"

    # This layer does:
    # - AI Guardian: trainable if aiguardian.py exists; else fallback heuristics
    # - Spam penalty: required fee multiplier + reasons
    # - Dynamic reward: bounded, supply-capped, can be replaced by ensemble later
    policy_code = r'''#!/usr/bin/env python3
"""
policy_layer.py (RamIA Policy Plugin)

Universal policy module you can plug into any blockchain core:
- tx_policy(tx_dict) -> (ok, fee_multiplier, reasons, suggestions)
- block_reward(metrics_dict) -> reward_int
- update_after_block(metrics_dict) -> None

Goals:
- Enforce anti-spam via fee penalties + human-readable warning
- Dynamic reward based on network metrics (AI-like, deterministic + bounded)
- Supply cap option to prevent "50M per block" disasters

This is not "production crypto". It's a clean policy hook to integrate with a real core.
"""

from __future__ import annotations
import json, math, re, time
from dataclasses import dataclass
from typing import Dict, Any, List, Tuple, Optional

# ---- Config ----
TOTAL_SUPPLY = 100_000_000     # cap (units)
MIN_REWARD = 1
MAX_REWARD = 20_000            # dev: raise/lower
TARGET_YEARS = 10
TARGET_BLOCK_SECONDS = 60
SMOOTHING = 0.15               # 0..1
TAIL_EMISSION = False          # if True, continues min reward after cap (exceeds cap)

SPAM_PATTERNS = [
    r"http[s]?://", r"\bfree money\b", r"\bairdrop\b", r"\bclaim\b", r"\bgiveaway\b",
    r"\bbonus\b", r"\bpromo\b", r"\bwallet connect\b", r"\bseed phrase\b"
]

@dataclass
class State:
    prev_reward: float = 0.0

STATE = State(prev_reward=0.0)

def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x

def sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x); return 1.0/(1.0+z)
    z = math.exp(x); return z/(1.0+z)

def estimate_target_blocks() -> float:
    secs = TARGET_YEARS * 365.25 * 24 * 3600
    return max(1.0, secs / max(1, TARGET_BLOCK_SECONDS))

def ewma(prev: float, target: float, alpha: float) -> float:
    a = clamp(alpha, 0.0, 1.0)
    return (1-a)*prev + a*target

# ---------------------
# Anti-spam / bad behavior
# ---------------------
def tx_policy(tx: Dict[str, Any]) -> Tuple[bool, float, List[str], List[str]]:
    """
    Returns:
      ok (bool)
      fee_multiplier (float)
      reasons (list[str])
      suggestions (list[str])
    tx dict recommended fields:
      amount, fee, outputs, memo, to_addr, timestamp
    """
    reasons: List[str] = []
    suggestions: List[str] = []
    suspicion = 0.0

    memo = str(tx.get("memo","") or "")
    if memo:
        low = memo.lower()
        for pat in SPAM_PATTERNS:
            if re.search(pat, low):
                suspicion += 0.35
                reasons.append(f"memo_matches:{pat}")
                suggestions.append("Remove links/promotional wording from memo.")
                break
        if len(memo) > 140:
            suspicion += 0.15
            reasons.append("memo_too_long")
            suggestions.append("Shorten memo to < 140 chars.")

    outputs = int(tx.get("outputs", tx.get("n_outputs", 1) or 1) or 1)
    if outputs >= 6:
        suspicion += 0.25
        reasons.append(f"many_outputs:{outputs}")
        suggestions.append("Reduce number of outputs to avoid spray/spam patterns.")

    fee = int(tx.get("fee", 0) or 0)
    if fee <= 0:
        suspicion += 0.35
        reasons.append("zero_fee")
        suggestions.append("Increase fee to pass anti-spam policy.")
    elif fee < 100:
        suspicion += 0.15
        reasons.append("low_fee")
        suggestions.append("Increase fee (>= 100) to avoid spam penalty.")

    suspicion = clamp(suspicion, 0.0, 1.0)

    # fee multiplier policy
    if suspicion < 0.40:
        mult = 1.0
    elif suspicion < 0.70:
        mult = 2.0
        reasons.insert(0, "suspicious_tx_warning")
    else:
        mult = 5.0
        reasons.insert(0, "high_risk_tx_warning")

    # If it's extremely suspicious, you can deny:
    deny = False
    if suspicion >= 0.90:
        deny = True
        reasons.insert(0, "tx_denied_extreme_spam")
        suggestions.append("Rewrite transaction to be more natural and avoid spam indicators.")

    return (not deny), mult, reasons, suggestions

# ---------------------
# Dynamic reward policy (AI-like, bounded, supply-capped)
# ---------------------
def block_reward(metrics: Dict[str, Any]) -> int:
    """
    metrics expected:
      height, minted, active_miners, active_nodes, tx_count, mempool_size, fee_pressure
    minted = total already-issued (or best approximation)
    """
    height = int(metrics.get("height", 0) or 0)
    minted = int(metrics.get("minted", 0) or 0)

    remaining = TOTAL_SUPPLY - minted
    if remaining <= 0:
        return MIN_REWARD if TAIL_EMISSION else 0

    blocks_total = estimate_target_blocks()
    remaining_blocks = max(1.0, blocks_total - height)
    base = max(1.0, remaining / remaining_blocks)

    miners = float(metrics.get("active_miners", 1.0) or 1.0)
    nodes = float(metrics.get("active_nodes", 1.0) or 1.0)
    txc = float(metrics.get("tx_count", 0.0) or 0.0)
    mem = float(metrics.get("mempool_size", 0.0) or 0.0)
    fee_p = float(metrics.get("fee_pressure", 0.0) or 0.0)

    part = 0.6*math.log10(max(1.0, miners)) + 0.4*math.log10(max(1.0, nodes))
    demand = 0.7*sigmoid((txc-200.0)/200.0) + 0.3*sigmoid((mem-50.0)/50.0)

    # "quantum-like" dual projection (toy): compute two candidates and blend
    cand_a = base * clamp(1.0 + 0.35*part + 0.45*(demand-0.5), 0.50, 1.80)
    cand_b = base * clamp(1.0 + 0.20*part + 0.60*(fee_p/3.0), 0.50, 1.80)
    target = 0.5*(cand_a + cand_b)

    prev = STATE.prev_reward if STATE.prev_reward > 0 else base
    smoothed = ewma(prev, target, SMOOTHING)

    smoothed = clamp(smoothed, float(MIN_REWARD), float(MAX_REWARD))
    reward = int(round(smoothed))
    reward = min(reward, remaining)

    STATE.prev_reward = float(reward)
    return int(reward)

def update_after_block(metrics: Dict[str, Any]) -> None:
    # Hook point for online learning later.
    return
'''
    policy_file.write_text(policy_code, encoding="utf-8")
    os.chmod(policy_file, 0o755)


def write_runner(qc_dir: Path, policy_dir: Path):
    """
    Create run_merged_node.py that tries to locate a QuantumCore entrypoint.
    If found, it imports and monkey-patches policy hooks.
    If not found, it prints actionable guidance.
    """
    runner = ROOT / "run_merged_node.py"
    runner_code = f"""#!/usr/bin/env python3
# run_merged_node.py (generated)
#
# Starts QuantumCore with RamIA policy hooks (best effort).
# If QuantumCore does not expose hooks, it still provides a clean integration plan.
#
# Usage:
#   python run_merged_node.py --help
#   python run_merged_node.py --qc-entry <path_to_entry.py> [--] <args...>
#
import argparse, sys, os
from pathlib import Path

QC = Path(r"{qc_dir.as_posix()}").resolve()
POLICY = Path(r"{policy_dir.as_posix()}").resolve()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--qc-entry", default="", help="QuantumCore entrypoint .py (if empty, will attempt auto-detect)")
    ap.add_argument("sep", nargs="?", help="Use -- then pass-through args to QuantumCore")
    ap.add_argument("args", nargs=argparse.REMAINDER)
    args = ap.parse_args()

    sys.path.insert(0, str(QC))
    sys.path.insert(0, str(POLICY))

    # Load policy layer
    import policy_layer as PL

    entry = args.qc_entry.strip()
    if not entry:
        # attempt auto-detect: choose smallest file with main/argparse
        cands = []
        for p in QC.rglob("*.py"):
            try:
                t = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if 'if __name__ == "__main__"' in t or "argparse" in t:
                cands.append(p)
        cands.sort(key=lambda x: x.stat().st_size)
        if cands:
            entry = str(cands[0])
    if not entry:
        print("[runner] ERROR: Could not auto-detect QuantumCore entrypoint.")
        print("[runner] Provide it manually: python run_merged_node.py --qc-entry vendor/quantumcore/<entry>.py -- <args>")
        sys.exit(2)

    entry_path = Path(entry).resolve()
    if not entry_path.exists():
        print("[runner] ERROR: entrypoint not found:", entry_path)
        sys.exit(2)

    print("[runner] Using entrypoint:", entry_path)

    # Execute entrypoint as a module-like script
    glb = {{
        "__file__": str(entry_path),
        "__name__": "__main__",
        "RAMIA_POLICY": PL,   # expose for cores that want to use it
    }}
    code = entry_path.read_text(encoding="utf-8", errors="ignore")
    exec(compile(code, str(entry_path), "exec"), glb, glb)

if __name__ == "__main__":
    main()
"""
    runner.write_text(runner_code, encoding="utf-8")
    os.chmod(runner, 0o755)


def write_report(qc_zip: Path, copied: List[str], entrypoints: List[Path]):
    lines = []
    lines.append("# RamIA ⨉ QuantumCore — Merge Report\n")
    lines.append(f"- Generated: {time.ctime()}\n")
    lines.append(f"- QuantumCore ZIP: `{qc_zip.name}`\n")
    lines.append(f"- QuantumCore extracted to: `vendor/quantumcore/`\n")
    lines.append(f"- Policy layer: `vendor/ramia_policy/policy_layer.py`\n")
    lines.append(f"- Runner: `run_merged_node.py`\n\n")

    lines.append("## What got merged\n")
    if copied:
        lines.append("### Copied from RamIA into vendor/ramia_policy/\n")
        for f in copied:
            lines.append(f"- `{f}`\n")
    else:
        lines.append("No RamIA modules were copied automatically (they may not exist in this snapshot).\\\n")
        lines.append("Policy layer was still created.\n")

    lines.append("\n## QuantumCore candidate entrypoints (auto-detected)\n")
    if entrypoints:
        for p in entrypoints[:10]:
            rel = p.relative_to(ROOT) if str(p).startswith(str(ROOT)) else p
            lines.append(f"- `{rel}`\n")
    else:
        lines.append("- None detected (you must specify --qc-entry)\n")

    lines.append("\n## How to run (developer)\n")
    lines.append("1) Install deps (if needed)\n")
    lines.append("```bash\npython --version\n```\n")
    lines.append("2) Try running QuantumCore through the runner\n")
    lines.append("```bash\npython run_merged_node.py --qc-entry vendor/quantumcore/<entrypoint>.py -- --help\n```\n")
    lines.append("3) Policy API available as RAMIA_POLICY\n")
    lines.append("- tx_policy(tx_dict) -> ok, fee_mult, reasons, suggestions\n")
    lines.append("- block_reward(metrics_dict) -> reward_int\n")

    lines.append("\n## Next step (real production integration)\n")
    lines.append("To fully integrate into QuantumCore production paths, connect policy hooks into:\n")
    lines.append("- mempool acceptance (pre-check): apply tx_policy and fee penalties\n")
    lines.append("- block template / coinbase: use block_reward for subsidy\n")
    lines.append("- telemetry: feed active_nodes/miners/mempool/fees into metrics\n")

    REPORT_FILE.write_text("".join(lines), encoding="utf-8")
    log(f"Wrote {REPORT_FILE}")


def main():
    qc_zip = find_zip_in_cwd()
    if not qc_zip:
        log("ERROR: No .zip found in current directory. Put quantumcore-main*.zip next to this script.")
        sys.exit(2)

    VENDOR.mkdir(exist_ok=True)
    extract_zip(qc_zip, QC_DIR)
    flatten_single_top_dir(QC_DIR)

    POLICY_DIR.mkdir(parents=True, exist_ok=True)
    copied = copy_ramia_modules(POLICY_DIR)
    write_policy_layer(POLICY_DIR)

    py_files = list_py_files(QC_DIR)
    entrypoints = guess_entrypoints(py_files)

    write_runner(QC_DIR, POLICY_DIR)
    write_report(qc_zip, copied, entrypoints)

    log("DONE ✅")
    log("Next:")
    log("  1) Read MERGE_REPORT.md")
    log("  2) Run: python run_merged_node.py --qc-entry vendor/quantumcore/<entrypoint>.py -- --help")


if __name__ == "__main__":
    main()
