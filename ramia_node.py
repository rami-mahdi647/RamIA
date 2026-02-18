#!/usr/bin/env python3
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

from ramia_rewards_ledger import append_reward
from ramia_reward_policy import RewardInputs, compute_reward

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
    rc = run_aichain(["--datadir", datadir, "mine", miner])
    if rc == 0:
        # Deterministic reward record (medium-security audit trail)
        # Work units: 1 per mined block (simple); improve later.
        # Policy-based deterministic reward (auditable)
        risk = 0.0
        nm = cfg.get('network_metrics', {})
        difficulty = float(nm.get('difficulty_estimate', 1.0))
        active_nodes = int(nm.get('active_nodes_estimate', 1))
        latency_ms = 0.0  # TODO: plug real measurement if you add networking
        inp = RewardInputs(difficulty=difficulty, latency_ms=latency_ms, active_nodes=active_nodes, risk=risk, work_units=1.0, event_ts=__import__('time').time().__int__())
        out = compute_reward(inp, cfg)
        append_reward({"type":"block","miner":miner,"work_units":1.0,"risk":risk,"reward":out.reward,"ref":"mine","breakdown":out.breakdown})
    return rc

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
