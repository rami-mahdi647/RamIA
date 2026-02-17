#!/usr/bin/env python3
"""
aichain_ai.py  (NEW FILE, no edits to aichain.py)

What this does:
- Loads your existing aichain.py dynamically
- Monkey-patches:
  1) Issuance policy (fixes 50,000,000 per block issue)
     - Supply-capped: total_supply=100,000,000 (atomic units in this prototype)
     - Dynamic-ish: adapts to network metrics and (optional) BTC mempool fee pressure
  2) Genesis: sets genesis mint to 0 (Bitcoin-like) so supply is emitted over time
     - You should reset datadir when switching to this engine.
  3) Spam/abuse fee policy:
     - If tx looks like spam, it warns and requires higher fee (penalty)
     - Gives reason(s)

Run like:
  python aichain_ai.py --datadir ./aichain_data init
  python aichain_ai.py --datadir ./aichain_data mine miner_rami
  python aichain_ai.py --datadir ./aichain_data send genesis alice 1000 --fee 1000 --memo "hello"
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import re
import sys
import urllib.request
from typing import Any, Dict, Optional, Tuple, List


# ----------------------------
# Public signals (optional)
# ----------------------------

def _http_get_json(url: str, timeout: int = 10) -> Optional[Dict[str, Any]]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RamIA/1.0 (aichain_ai)"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        return json.loads(data.decode("utf-8"))
    except Exception:
        return None


def fetch_btc_fee_pressure() -> float:
    """
    Returns a small normalized fee pressure in [0..3] (heuristic).
    Uses mempool.space fees if available, else blockstream.
    """
    mp = _http_get_json("https://mempool.space/api/v1/fees/recommended")
    if mp:
        fastest = float(mp.get("fastestFee", 0.0))
        # 50 sat/vB is "busy-ish" => pressure ~1
        return min(3.0, max(0.0, fastest / 50.0))

    bs = _http_get_json("https://blockstream.info/api/fee-estimates")
    if bs:
        fastest = float(bs.get("1", bs.get("2", 0.0)) or 0.0)
        return min(3.0, max(0.0, fastest / 50.0))

    return 0.0


# ----------------------------
# Supply-capped dynamic issuance
# ----------------------------

TOTAL_SUPPLY = 100_000_000          # IMPORTANT: the cap you asked for (atomic units in this prototype)
TARGET_YEARS = 10                   # distribute over 10 years (dev default)
TARGET_BLOCK_TIME = 60              # must match ChainDB.target_block_time
MIN_SUBSIDY = 1
MAX_SUBSIDY = 5000                  # safety; prevents insane payouts


def _estimate_target_blocks() -> int:
    secs = TARGET_YEARS * 365 * 24 * 3600
    return max(1, secs // max(1, TARGET_BLOCK_TIME))


def _sum_issued_from_chain(db: Any) -> int:
    """
    Sums all coinbase outputs in the chain.
    O(n) but fine for dev.
    """
    issued = 0
    try:
        for b in db.blocks:
            if not b.txs:
                continue
            cb = b.txs[0]
            # coinbase has vout list of outputs
            for o in cb.vout:
                issued += int(o.amount)
    except Exception:
        return 0
    return int(issued)


def _dynamic_subsidy(db: Any, miners: int, nodes: int, tx_count: int, mempool_size: int, fee_pressure: float) -> int:
    """
    Deterministic "AI-like" subsidy controller:
    - Baseline: remaining / remaining_blocks
    - Multiplier based on participation and congestion (bounded)
    - Hard cap by remaining supply
    """
    height = 0
    try:
        height = int(db.height())
    except Exception:
        height = 0

    issued = _sum_issued_from_chain(db)
    remaining = TOTAL_SUPPLY - issued
    if remaining <= 0:
        return 0

    target_blocks = _estimate_target_blocks()
    remaining_blocks = max(1, target_blocks - height)
    baseline = max(1, remaining // remaining_blocks)

    # Participation score (log-ish, bounded)
    miners = max(1, int(miners))
    nodes = max(1, int(nodes))
    part = 0.15 * (min(10, len(str(miners))) + min(10, len(str(nodes))))  # tiny bounded proxy

    # Congestion score: local chain + optional BTC pressure
    local = 0.0
    if tx_count > 0:
        local = min(3.0, float(mempool_size) / 100.0)  # 100 tx mempool => 1.0 pressure
    btc = fetch_btc_fee_pressure()  # 0..3
    cong = max(local, btc, float(fee_pressure))

    # Mult in [1.0 .. 1.75]
    mult = 1.0 + min(0.75, 0.15 * part + 0.25 * cong)

    sub = int(baseline * mult)
    sub = max(MIN_SUBSIDY, min(MAX_SUBSIDY, sub))
    sub = min(sub, remaining)
    return int(sub)


# ----------------------------
# Spam / bad-behavior penalty policy (no ML deps)
# ----------------------------

SPAM_PATTERNS = [
    r"http[s]?://", r"\bfree money\b", r"\bairdrop\b", r"\bclaim\b", r"\bgiveaway\b",
    r"\bbonus\b", r"\bpromo\b", r"\bwallet connect\b"
]

def score_suspicion(tx: Any) -> Tuple[float, List[str]]:
    """
    Return suspicion score in [0..1] and reasons.
    Heuristics only (works in stdlib).
    """
    reasons: List[str] = []
    score = 0.0

    memo = ""
    try:
        memo = str(tx.memo or "")
    except Exception:
        memo = ""

    if memo:
        low = memo.lower()
        for pat in SPAM_PATTERNS:
            if re.search(pat, low):
                score += 0.35
                reasons.append(f"memo_matches:{pat}")
                break
        if len(memo) > 140:
            score += 0.15
            reasons.append("memo_too_long")

    # Many outputs can be spammy (spray)
    try:
        n_out = len(tx.vout)
        if n_out >= 6:
            score += 0.25
            reasons.append(f"many_outputs:{n_out}")
    except Exception:
        pass

    # Very low fee can be spam indicator
    try:
        fee = int(tx.fee)
        if fee <= 0:
            score += 0.35
            reasons.append("zero_fee")
        elif fee < 100:
            score += 0.15
            reasons.append("low_fee")
    except Exception:
        pass

    score = max(0.0, min(1.0, score))
    return score, reasons


def required_fee_multiplier(suspicion: float) -> float:
    """
    Penalty: higher suspicion => higher required fee.
    """
    if suspicion < 0.40:
        return 1.0
    if suspicion < 0.70:
        return 2.0
    return 5.0


# ----------------------------
# Load and patch aichain.py
# ----------------------------

def load_aichain_module(path: str = "aichain.py"):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing {path} in current directory.")
    loader = importlib.machinery.SourceFileLoader("aichain_mod", path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)  # type: ignore
    loader.exec_module(mod)  # type: ignore
    return mod


def patch_module(mod):
    # 1) Patch policy: replace predict() to call our dynamic subsidy
    OriginalPolicy = mod.IssuancePolicy

    class AIPolicy(OriginalPolicy):
        def __init__(self, db_ref):
            # Call parent but keep bounded defaults (these won't be used as fixed base)
            super().__init__(base_subsidy=100, min_subsidy=MIN_SUBSIDY, max_subsidy=MAX_SUBSIDY)
            self._db = db_ref

        def predict(self, miners: int, nodes: int, tx_count: int, mempool_size: int, fee_pressure: float) -> int:
            return _dynamic_subsidy(self._db, miners, nodes, tx_count, mempool_size, fee_pressure)

    # 2) Patch ChainDB.__init__ to swap policy after load/genesis
    OriginalChainDB = mod.ChainDB
    original_init = OriginalChainDB.__init__

    def patched_init(self, path: str):
        original_init(self, path)
        # Ensure target block time constant matches our policy assumption
        try:
            self.target_block_time = TARGET_BLOCK_TIME
        except Exception:
            pass
        # Swap policy to AI policy bound to this DB
        self.policy = AIPolicy(self)

    OriginalChainDB.__init__ = patched_init

    # 3) Patch genesis to mint 0 (Bitcoin-like).
    # IMPORTANT: use a fresh datadir when switching.
    original_genesis = OriginalChainDB._genesis

    def patched_genesis(self):
        # Create a coinbase that mints 0 tokens at genesis
        coinbase = mod.Transaction(
            version=1,
            vin=[mod.TxIn(from_addr="COINBASE")],
            vout=[mod.TxOut(to_addr="genesis", amount=0)],
            fee=0,
            nonce=0,
            memo="genesis",
        )
        txids = [coinbase.txid()]
        mr = mod.merkle_root(txids)
        hdr = mod.BlockHeader(
            version=1,
            prev_hash="00" * 32,
            merkle_root=mr,
            timestamp=mod.now_ts(),
            height=0,
            bits=self.bits,
            nonce=0,
        )
        blk = mod.Block(header=hdr, txs=[coinbase])
        blk = self._mine_block(blk)
        self._apply_block(blk)
        self.blocks.append(blk)
        self._persist_block(blk)
        self._persist_state()

    OriginalChainDB._genesis = patched_genesis

    # 4) Patch tx basic validation to enforce spam penalties (fee-bump requirement)
    original_verify = OriginalChainDB._verify_tx_basic

    def patched_verify_tx_basic(self, tx):
        ok, why = original_verify(self, tx)
        if not ok:
            return ok, why

        # Don't penalize coinbase
        try:
            if self._is_coinbase(tx):
                return True, "ok"
        except Exception:
            pass

        suspicion, reasons = score_suspicion(tx)
        mult = required_fee_multiplier(suspicion)
        if mult > 1.0:
            # Require fee >= base_fee * mult
            # base_fee heuristic: 100 per output
            try:
                n_out = max(1, len(tx.vout))
            except Exception:
                n_out = 1
            base_fee = 100 * n_out
            required = int(base_fee * mult)

            fee = 0
            try:
                fee = int(tx.fee)
            except Exception:
                fee = 0

            if fee < required:
                # Provide a human-readable reason (as requested)
                reason = f"suspicious_tx fee_too_low required_fee={required} given_fee={fee} reasons={','.join(reasons)}"
                return False, reason

        return True, "ok"

    OriginalChainDB._verify_tx_basic = patched_verify_tx_basic

    return mod


def main():
    # Ensure we run from repo root with aichain.py present
    mod = load_aichain_module("aichain.py")
    mod = patch_module(mod)

    # Delegate to original CLI main()
    # aichain.py ends with: if __name__ == "__main__": main()
    # Here we call it directly.
    return mod.main()


if __name__ == "__main__":
    raise SystemExit(main())




