#!/usr/bin/env python3
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
