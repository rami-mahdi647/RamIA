#!/usr/bin/env python3
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
