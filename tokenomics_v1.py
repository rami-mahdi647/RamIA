#!/usr/bin/env python3
"""Tokenomics v1 math and deterministic sanity checks for RamIA."""

from __future__ import annotations

import argparse
from dataclasses import dataclass

TOTAL_SUPPLY = 100_000_000


@dataclass(frozen=True)
class Allocation:
    name: str
    percent: int
    amount: int


@dataclass(frozen=True)
class VestingSchedule:
    cliff_sec: int
    duration_sec: int


ALLOCATIONS = (
    Allocation("community", 45, 45_000_000),
    Allocation("team", 15, 15_000_000),
    Allocation("treasury", 15, 15_000_000),
    Allocation("founder", 10, 10_000_000),
    Allocation("market_incentives", 10, 10_000_000),
    Allocation("liquidity", 5, 5_000_000),
)


VESTING = {
    "team": VestingSchedule(cliff_sec=365 * 24 * 3600, duration_sec=48 * 30 * 24 * 3600),
    "treasury": VestingSchedule(cliff_sec=365 * 24 * 3600, duration_sec=36 * 30 * 24 * 3600),
    "founder": VestingSchedule(cliff_sec=365 * 24 * 3600, duration_sec=48 * 30 * 24 * 3600),
}


def total_supply() -> int:
    return TOTAL_SUPPLY


def allocation_table() -> dict[str, int]:
    return {a.name: a.amount for a in ALLOCATIONS}


def vesting_unlock(amount: int, start_ts: int, now_ts: int, cliff_sec: int, duration_sec: int) -> int:
    if amount <= 0:
        return 0
    if now_ts <= start_ts + max(cliff_sec, 0):
        return 0
    if duration_sec <= 0:
        return amount
    elapsed = min(max(0, now_ts - start_ts - max(cliff_sec, 0)), duration_sec)
    unlocked = (amount * elapsed) // duration_sec
    return min(amount, max(0, unlocked))


def apply_ai_multiplier(metrics: dict) -> float:
    # deterministic simple score using bounded inputs
    activity = float(metrics.get("activity", 1.0))
    stability = float(metrics.get("stability", 1.0))
    demand = float(metrics.get("demand", 1.0))
    raw = 0.55 + (0.25 * activity) + (0.10 * stability) + (0.10 * demand)
    return max(0.5, min(1.5, raw))


def compute_block_reward(state_metrics: dict, remaining_pool: int, epochs_remaining: int) -> int:
    if remaining_pool <= 0:
        return 0
    safe_epochs = max(1, int(epochs_remaining))
    baseline = max(1, remaining_pool // safe_epochs)
    reward = int(baseline * apply_ai_multiplier(state_metrics))
    reward = max(0, reward)
    return min(reward, remaining_pool)


def _self_test() -> None:
    table = allocation_table()
    assert sum(table.values()) == total_supply(), "allocation sum must equal total supply"

    # vesting checks
    amount = 1_000_000
    start = 1_700_000_000
    cliff = 365 * 24 * 3600
    duration = 36 * 30 * 24 * 3600
    assert vesting_unlock(amount, start, start + cliff, cliff, duration) == 0
    assert vesting_unlock(amount, start, start + cliff + duration, cliff, duration) == amount

    half = vesting_unlock(amount, start, start + cliff + (duration // 2), cliff, duration)
    assert 490_000 <= half <= 510_000, f"expected near half unlock, got {half}"

    # multiplier checks
    assert apply_ai_multiplier({"activity": -10, "stability": -10, "demand": -10}) == 0.5
    assert apply_ai_multiplier({"activity": 10, "stability": 10, "demand": 10}) == 1.5

    # reward checks
    r = compute_block_reward({"activity": 1, "stability": 1, "demand": 1}, 10_000, 100)
    assert 50 <= r <= 150
    assert compute_block_reward({}, 0, 10) == 0
    assert compute_block_reward({}, 10, 10_000_000) <= 10

    # supply safety simulation
    remaining = 1000
    minted = 0
    for _ in range(5000):
        reward = compute_block_reward({"activity": 1.0, "stability": 1.0, "demand": 1.0}, remaining, 100)
        minted += reward
        remaining -= reward
        if remaining == 0:
            break
    assert minted <= 1000
    assert remaining >= 0
    assert minted + remaining == 1000

    print("tokenomics_v1 self-test: PASS")


def main() -> None:
    parser = argparse.ArgumentParser(prog="tokenomics_v1")
    parser.add_argument("--self-test", action="store_true", help="run deterministic sanity checks")
    args = parser.parse_args()
    if args.self_test:
        _self_test()
        return
    print("total_supply", total_supply())
    print("allocations", allocation_table())


if __name__ == "__main__":
    main()
