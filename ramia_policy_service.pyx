#!/usr/bin/env python3
"""
ramia_policy_service.py (stdlib-only)

Universal Policy Sidecar for ANY core (Node/TS/Rust/Go/C++).

Endpoints:
  POST /tx_policy
    body: {amount, fee, outputs, memo, to_addr, timestamp}
    resp: {ok, fee_multiplier, reasons[], suggestions[], suspicion}

  POST /block_reward
    body: {height, minted, active_miners, active_nodes, tx_count, mempool_size, fee_pressure}
    resp: {reward, debug}

Run:
  python3 ramia_policy_service.py --host 127.0.0.1 --port 8787
"""

from __future__ import annotations
import argparse
import json
import math
import re
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Any, List, Tuple

# -----------------------
# Config (edit safely)
# -----------------------
TOTAL_SUPPLY = 100_000_000
MIN_REWARD = 1
MAX_REWARD = 20_000
TARGET_YEARS = 10
TARGET_BLOCK_SECONDS = 60
SMOOTHING = 0.15
TAIL_EMISSION = False

SPAM_PATTERNS = [
    r"http[s]?://", r"\bfree money\b", r"\bairdrop\b", r"\bclaim\b", r"\bgiveaway\b",
    r"\bbonus\b", r"\bpromo\b", r"\bwallet connect\b", r"\bseed phrase\b",
    r"\bpassword\b", r"\btelegram\b"
]

STATE = {"prev_reward": 0.0}

def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x

def sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x); return 1.0/(1.0+z)
    z = math.exp(x); return z/(1.0+z)

def ewma(prev: float, target: float, alpha: float) -> float:
    a = clamp(alpha, 0.0, 1.0)
    return (1-a)*prev + a*target

def estimate_target_blocks() -> float:
    secs = TARGET_YEARS * 365.25 * 24 * 3600
    return max(1.0, secs / max(1, TARGET_BLOCK_SECONDS))

# -----------------------
# TX policy: anti-spam + penalties + reasons/suggestions
# -----------------------
def tx_policy(tx: Dict[str, Any]) -> Tuple[bool, float, List[str], List[str], float]:
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
                suggestions.append("Remove links/promotional/suspicious wording from memo.")
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
        suggestions.append("Increase fee (>= 100) to reduce suspicion.")

    amount = float(tx.get("amount", 0) or 0)
    if amount > 0 and fee > 0 and fee / max(1.0, amount) < 0.00001:
        suspicion += 0.10
        reasons.append("fee_to_amount_ratio_low")
        suggestions.append("Increase fee or split amount more naturally.")

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

    deny = False
    if suspicion >= 0.90:
        deny = True
        reasons.insert(0, "tx_denied_extreme_spam")
        suggestions.append("Rewrite transaction to remove spam indicators.")

    return (not deny), float(mult), reasons, suggestions, float(suspicion)

# -----------------------
# Reward policy: dynamic + bounded + supply-capped
# -----------------------
def block_reward(metrics: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    height = int(metrics.get("height", 0) or 0)
    minted = int(metrics.get("minted", 0) or 0)

    remaining = TOTAL_SUPPLY - minted
    if remaining <= 0:
        r = MIN_REWARD if TAIL_EMISSION else 0
        return r, {"mode": "tail" if TAIL_EMISSION else "cap_reached", "remaining": remaining}

    blocks_total = estimate_target_blocks()
    remaining_blocks = max(1.0, blocks_total - height)
    base = max(1.0, remaining / remaining_blocks)

    miners = float(metrics.get("active_miners", 1.0) or 1.0)
    nodes = float(metrics.get("active_nodes", 1.0) or 1.0)
    txc = float(metrics.get("tx_count", 0.0) or 0.0)
    mem = float(metrics.get("mempool_size", 0.0) or 0.0)
    fee_p = float(metrics.get("fee_pressure", 0.0) or 0.0)

    part = 0.6 * math.log10(max(1.0, miners)) + 0.4 * math.log10(max(1.0, nodes))
    demand = 0.7 * sigmoid((txc - 200.0) / 200.0) + 0.3 * sigmoid((mem - 50.0) / 50.0)

    # “32 nets / quantum-like” concept (deterministic placeholder):
    # Two projections -> blend (you can extend to 32 later).
    cand_a = base * clamp(1.0 + 0.35*part + 0.45*(demand - 0.5), 0.50, 1.80)
    cand_b = base * clamp(1.0 + 0.20*part + 0.60*(fee_p/3.0), 0.50, 1.80)
    target = 0.5 * (cand_a + cand_b)

    prev = float(STATE.get("prev_reward", 0.0) or 0.0)
    if prev <= 0:
        prev = base
    smoothed = ewma(prev, target, SMOOTHING)

    smoothed = clamp(smoothed, float(MIN_REWARD), float(MAX_REWARD))
    reward = int(round(smoothed))
    reward = min(reward, max(0, remaining))

    STATE["prev_reward"] = float(reward)

    dbg = {
        "height": height,
        "minted": minted,
        "remaining": remaining,
        "base": base,
        "cand_a": cand_a,
        "cand_b": cand_b,
        "target": target,
        "smoothed": smoothed,
        "reward": reward,
        "miners": miners,
        "nodes": nodes,
        "tx_count": txc,
        "mempool_size": mem,
        "fee_pressure": fee_p,
    }
    return reward, dbg

# -----------------------
# HTTP server
# -----------------------
class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, obj: Dict[str, Any]):
        body = json.dumps(obj, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"ok": True, "ts": int(time.time())})
            return
        self._send(404, {"ok": False, "error": "not_found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(n) if n > 0 else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            self._send(400, {"ok": False, "error": "bad_json"})
            return

        if self.path == "/tx_policy":
            ok, mult, reasons, suggestions, suspicion = tx_policy(data)
            self._send(200, {
                "ok": ok,
                "fee_multiplier": mult,
                "reasons": reasons,
                "suggestions": suggestions,
                "suspicion": suspicion,
            })
            return

        if self.path == "/block_reward":
            reward, dbg = block_reward(data)
            self._send(200, {"ok": True, "reward": reward, "debug": dbg})
            return

        self._send(404, {"ok": False, "error": "not_found"})

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()

    srv = HTTPServer((args.host, args.port), Handler)
    print(f"[policy] listening on http://{args.host}:{args.port}")
    srv.serve_forever()

if __name__ == "__main__":
    main()
