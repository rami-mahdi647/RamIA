#!/usr/bin/env python3
from __future__ import annotations
"""
Medium-security, auditable reward policy.
Deterministic + bounded + config-driven (ramia_config.json).
"""
from dataclasses import dataclass
from typing import Any, Dict
import time

def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x

@dataclass(frozen=True)
class RewardInputs:
    difficulty: float
    latency_ms: float
    active_nodes: int
    risk: float
    work_units: float
    event_ts: int

@dataclass(frozen=True)
class RewardOutput:
    reward: float
    breakdown: Dict[str, float]

def load_policy(cfg: Dict[str, Any]) -> Dict[str, Any]:
    tok = cfg.setdefault("tokenomics", {})
    tok.setdefault("max_supply", 100_000_000.0)
    tok.setdefault("genesis_supply", 0.0)

    tok.setdefault("base_block_reward", 1.0)
    tok.setdefault("max_reward_per_event", 25.0)
    tok.setdefault("min_reward_per_event", 0.0)

    tok.setdefault("difficulty_weight", 0.25)
    tok.setdefault("latency_weight", 0.15)
    tok.setdefault("latency_target_ms", 250.0)
    tok.setdefault("nodes_weight", 0.20)
    tok.setdefault("nodes_target", 5)
    tok.setdefault("risk_penalty", 0.50)

    tok.setdefault("difficulty_factor_min", 0.75)
    tok.setdefault("difficulty_factor_max", 2.50)
    tok.setdefault("latency_factor_min", 0.50)
    tok.setdefault("latency_factor_max", 1.50)
    tok.setdefault("nodes_factor_min", 0.75)
    tok.setdefault("nodes_factor_max", 1.75)
    return tok

def difficulty_factor(difficulty: float, tok: Dict[str, Any]) -> float:
    w = float(tok["difficulty_weight"])
    raw = 1.0 + w * (difficulty ** 0.5)
    return _clamp(raw, float(tok["difficulty_factor_min"]), float(tok["difficulty_factor_max"]))

def latency_factor(latency_ms: float, tok: Dict[str, Any]) -> float:
    target = float(tok["latency_target_ms"]) or 250.0
    lat = max(1.0, float(latency_ms))
    raw = target / lat
    return _clamp(raw, float(tok["latency_factor_min"]), float(tok["latency_factor_max"]))

def nodes_factor(active_nodes: int, tok: Dict[str, Any]) -> float:
    target = int(tok["nodes_target"]) if int(tok["nodes_target"]) > 0 else 5
    n = max(1, int(active_nodes))
    raw = n / float(target)
    return _clamp(raw, float(tok["nodes_factor_min"]), float(tok["nodes_factor_max"]))

def compute_reward(inp: RewardInputs, cfg: Dict[str, Any]) -> RewardOutput:
    tok = load_policy(cfg)

    base = float(tok["base_block_reward"]) * float(inp.work_units)
    df = difficulty_factor(float(inp.difficulty), tok)
    lf = latency_factor(float(inp.latency_ms), tok)
    nf = nodes_factor(int(inp.active_nodes), tok)

    lat_w = float(tok["latency_weight"])
    nod_w = float(tok["nodes_weight"])
    lat_mult = 1.0 + lat_w * (lf - 1.0)
    nod_mult = 1.0 + nod_w * (nf - 1.0)

    risk = _clamp(float(inp.risk), 0.0, 1.0)
    rp = float(tok["risk_penalty"])
    risk_mult = max(0.0, 1.0 - risk * rp)

    reward = base * df * lat_mult * nod_mult * risk_mult
    reward = _clamp(reward, float(tok["min_reward_per_event"]), float(tok["max_reward_per_event"]))

    return RewardOutput(
        reward=float(reward),
        breakdown={
            "base": base,
            "difficulty_factor": df,
            "latency_factor": lf,
            "latency_mult": lat_mult,
            "nodes_factor": nf,
            "nodes_mult": nod_mult,
            "risk": risk,
            "risk_mult": risk_mult,
        },
    )

def now_ts() -> int:
    return int(time.time())

if __name__ == "__main__":
    print("ramia_reward_policy.py ok")
