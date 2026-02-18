#!/usr/bin/env python3
from __future__ import annotations
# ramia_rewards_ledger.py
# Append-only rewards ledger with hash chaining (tamper-evident).
# "Medium security": integrity, reproducibility, minimal attack surface.

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

DEFAULT_LEDGER = Path("./aichain_data/rewards_ledger.jsonl")

def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def _canon(obj: Dict[str, Any]) -> bytes:
    # Canonical JSON for deterministic hashing
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def last_entry(ledger_path: Path = DEFAULT_LEDGER) -> Optional[Dict[str, Any]]:
    if not ledger_path.exists():
        return None
    with ledger_path.open("rb") as f:
        f.seek(0, 2)
        end = f.tell()
        if end == 0:
            return None
        pos = end - 1
        while pos > 0:
            f.seek(pos)
            if f.read(1) == b"\n":
                break
            pos -= 1
        f.seek(pos + 1 if pos > 0 else 0)
        line = f.readline().decode("utf-8").strip()
        if not line:
            return None
        return json.loads(line)

def append_reward(event: Dict[str, Any], ledger_path: Path = DEFAULT_LEDGER) -> Dict[str, Any]:
    """
    event should include:
      - type: "block" | "tx" | "contribution"
      - miner / addr / node_id
      - work_units (float/int)
      - risk (float)
      - reward (float)
      - ref: txid or block hash/height
    """
    ledger_path.parent.mkdir(parents=True, exist_ok=True)

    prev = last_entry(ledger_path)
    prev_hash = prev["entry_hash"] if prev else "0" * 64

    entry = {
        "v": 1,
        "ts": int(time.time()),
        "prev_hash": prev_hash,
        "event": event,
    }
    entry_hash = _sha256(_canon(entry))
    record = dict(entry)
    record["entry_hash"] = entry_hash

    with ledger_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return record

def verify_ledger(ledger_path: Path = DEFAULT_LEDGER) -> Tuple[bool, str]:
    if not ledger_path.exists():
        return True, "ledger missing (ok)"
    prev_hash = "0" * 64
    line_no = 0
    with ledger_path.open("r", encoding="utf-8") as f:
        for line in f:
            line_no += 1
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            entry_hash = rec.get("entry_hash", "")
            entry = {
                "v": rec.get("v"),
                "ts": rec.get("ts"),
                "prev_hash": rec.get("prev_hash"),
                "event": rec.get("event"),
            }
            if entry["prev_hash"] != prev_hash:
                return False, f"broken chain at line {line_no} (prev_hash mismatch)"
            calc = _sha256(_canon(entry))
            if calc != entry_hash:
                return False, f"tamper detected at line {line_no} (hash mismatch)"
            prev_hash = entry_hash
    return True, "ok"

if __name__ == "__main__":
    ok, msg = verify_ledger()
    print("ok" if ok else "fail", msg)
