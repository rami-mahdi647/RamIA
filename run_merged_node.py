#!/usr/bin/env python3
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

QC = Path(r"/data/data/com.termux/files/home/RamIA/vendor/quantumcore").resolve()
POLICY = Path(r"/data/data/com.termux/files/home/RamIA/vendor/ramia_policy").resolve()

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
    glb = {
        "__file__": str(entry_path),
        "__name__": "__main__",
        "RAMIA_POLICY": PL,   # expose for cores that want to use it
    }
    code = entry_path.read_text(encoding="utf-8", errors="ignore")
    exec(compile(code, str(entry_path), "exec"), glb, glb)

if __name__ == "__main__":
    main()
