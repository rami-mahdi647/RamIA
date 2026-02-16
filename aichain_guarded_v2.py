#!/usr/bin/env python3
# AIChain Guarded Bridge v2
# - Runtime patch only (monkeypatch). No edits to aichain.py or aiguardian.py
# - Adds: quarantine pool, rate limiting, dynamic threshold

import argparse
import json
import time
from typing import Any, Dict, Optional, Tuple

import aichain
import aiguardian


def _tx_sender(tx: "aichain.Transaction") -> str:
    if not tx.vin:
        return ""
    return tx.vin[0].from_addr or ""


def _tx_to_guardian_dict(tx: "aichain.Transaction") -> Dict[str, Any]:
    amount = float(sum(o.amount for o in tx.vout))
    fee = float(tx.fee)
    outputs = int(len(tx.vout))
    memo = str(tx.memo or "")
    to_addr = tx.vout[0].to_addr if tx.vout else ""
    return {
        "amount": amount,
        "fee": fee,
        "outputs": outputs,
        "memo": memo,
        "to_addr": to_addr,
        "burst_score": 0.0,
        "timestamp": int(aichain.now_ts()),
    }


class RateLimiter:
    """
    Token-bucket-ish limiter per sender.
    max_events per window_seconds. Cheap and deterministic.
    """
    def __init__(self, max_events: int, window_seconds: int):
        self.max_events = max_events
        self.window = window_seconds
        self.events: Dict[str, list] = {}

    def allow(self, key: str, ts: int) -> bool:
        if not key:
            return True
        lst = self.events.get(key, [])
        cutoff = ts - self.window
        lst = [t for t in lst if t >= cutoff]
        if len(lst) >= self.max_events:
            self.events[key] = lst
            return False
        lst.append(ts)
        self.events[key] = lst
        return True


def install_guardian_patch(
    model_path: str,
    base_threshold: float,
    mode: str = "quarantine",
    json_log_path: Optional[str] = None,
    quarantine_path: Optional[str] = None,
    rate_max: int = 15,
    rate_window_sec: int = 60,
    dynamic_threshold: bool = True,
    dyn_mempool_target: int = 2000,
    dyn_slope: float = 0.15,
) -> Tuple[bool, str]:
    """
    mode:
      - deny: reject if score >= threshold
      - quarantine: put suspicious tx into db.quarantine dict (and optionally persist JSONL)
      - fee-bump: require fee >= base + k*score if suspicious
      - tag-only: never reject; just log

    dynamic_threshold:
      - threshold increases when mempool is large (stricter under congestion)
    """
    if not model_path:
        return False, "guardian model path missing"

    model = aiguardian.LogisticModel.load(model_path)
    guardian = aiguardian.Guardian(model, threshold=base_threshold)

    limiter = RateLimiter(max_events=rate_max, window_seconds=rate_window_sec)

    original_add = aichain.ChainDB.add_tx_to_mempool

    def _effective_threshold(self: "aichain.ChainDB") -> float:
        th = float(base_threshold)
        if dynamic_threshold:
            m = float(len(self.mempool))
            # When mempool > target, increase threshold strictness by lowering acceptance.
            # Here: effective threshold becomes smaller? Actually score >= threshold rejects,
            # so making threshold lower is stricter. We'll decrease threshold as mempool grows.
            # Clamp to sane range.
            over = max(0.0, (m - float(dyn_mempool_target)) / max(1.0, float(dyn_mempool_target)))
            th = th - dyn_slope * over
            th = min(0.99, max(0.05, th))
        return th

    def _log(payload: Dict[str, Any]):
        if not json_log_path:
            return
        try:
            with open(json_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, sort_keys=True) + "\n")
        except Exception:
            pass

    def _quarantine_append(payload: Dict[str, Any]):
        if not quarantine_path:
            return
        try:
            with open(quarantine_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, sort_keys=True) + "\n")
        except Exception:
            pass

    def guarded_add(self: "aichain.ChainDB", tx: "aichain.Transaction"):
        # Ensure quarantine storage exists on DB instance
        if not hasattr(self, "quarantine"):
            self.quarantine = {}  # type: ignore[attr-defined]

        # Coinbase should never enter mempool anyway; pass-through
        if len(tx.vin) == 1 and tx.vin[0].from_addr == "COINBASE":
            return original_add(self, tx)

        ts = int(aichain.now_ts())
        sender = _tx_sender(tx)

        # Rate limit before ML
        if not limiter.allow(sender, ts):
            payload = {
                "ts": ts,
                "txid": tx.txid(),
                "sender": sender,
                "decision": "deny",
                "reason": "rate_limited",
            }
            _log(payload)
            return (False, "rate limited")

        tx_dict = _tx_to_guardian_dict(tx)
        score = guardian.score(tx_dict)
        th = _effective_threshold(self)

        decision = "allow"
        reason = "ok"

        if mode == "deny":
            if score >= th:
                decision = "deny"
                reason = "guardian_threshold_exceeded"
                payload = {
                    "ts": ts, "txid": tx.txid(), "sender": sender,
                    "score": float(score), "threshold": float(th),
                    "mode": mode, "decision": decision, "reason": reason,
                }
                _log(payload)
                return (False, f"guardian denied: score={score:.6f} >= {th:.6f}")
            res = original_add(self, tx)

        elif mode == "quarantine":
            if score >= th:
                decision = "quarantine"
                reason = "guardian_threshold_exceeded"
                txid = tx.txid()
                # store tx serialized; keep minimal
                self.quarantine[txid] = tx.to_dict()  # type: ignore[attr-defined]
                payload = {
                    "ts": ts, "txid": txid, "sender": sender,
                    "score": float(score), "threshold": float(th),
                    "mode": mode, "decision": decision, "reason": reason,
                    "tx": tx.to_dict(),
                }
                _log(payload)
                _quarantine_append(payload)
                return (False, f"quarantined: score={score:.6f} >= {th:.6f}")
            res = original_add(self, tx)

        elif mode == "fee-bump":
            required_fee = int(1000 + (score * 100000))
            if score >= th and tx.fee < required_fee:
                decision = "deny"
                reason = "guardian_fee_bump_required"
                payload = {
                    "ts": ts, "txid": tx.txid(), "sender": sender,
                    "score": float(score), "threshold": float(th),
                    "required_fee": int(required_fee),
                    "fee": int(tx.fee),
                    "mode": mode, "decision": decision, "reason": reason,
                }
                _log(payload)
                return (False, f"fee-bump: fee={tx.fee} < required_fee={required_fee} (score={score:.6f}, th={th:.6f})")
            res = original_add(self, tx)

        elif mode == "tag-only":
            res = original_add(self, tx)

        else:
            return (False, f"unknown guardian mode: {mode}")

        # log allow result too
        payload = {
            "ts": ts, "txid": tx.txid(), "sender": sender,
            "score": float(score), "threshold": float(th),
            "mode": mode, "decision": decision, "reason": reason,
            "mempool_size": int(len(self.mempool)),
        }
        _log(payload)
        return res

    aichain.ChainDB.add_tx_to_mempool = guarded_add  # type: ignore[attr-defined]
    return True, "guardian patch installed (v2)"


# ---- Commands mirror aichain ----

def cmd_init(args):
    db = aichain.ChainDB(args.datadir)
    print("ok")
    print("height", db.height())
    print("tip", db.tip().block_hash())

def cmd_balance(args):
    db = aichain.ChainDB(args.datadir)
    print(db.balances.get(args.addr, 0))

def cmd_send(args):
    db = aichain.ChainDB(args.datadir)
    tx = db.make_tx(args.from_addr, args.to_addr, args.amount, args.fee, memo=args.memo)
    ok, out = db.add_tx_to_mempool(tx)
    if not ok:
        print("error", out)
        return
    print("txid", out)

def cmd_mine(args):
    db = aichain.ChainDB(args.datadir)
    tpl = db.build_block_template(args.miner_addr)
    mined = db._mine_block(tpl)
    ok, why = db.submit_block(mined)
    if not ok:
        print("error", why)
        return
    print("ok accepted")
    print("height", db.height())
    print("hash", mined.block_hash())
    print("coinbase_paid", sum(o.amount for o in mined.txs[0].vout))

def cmd_chain(args):
    db = aichain.ChainDB(args.datadir)
    for b in db.blocks[-args.n:]:
        print(b.header.height, b.block_hash(), b.header.timestamp, "txs", len(b.txs), "bits", b.header.bits)

def cmd_quarantine(args):
    db = aichain.ChainDB(args.datadir)
    q = getattr(db, "quarantine", {})
    print(json.dumps({"quarantine_size": len(q), "sample_txids": list(q.keys())[: args.n]}, indent=2))


def main():
    p = argparse.ArgumentParser(prog="aichain_guarded_v2")
    p.add_argument("--datadir", default="./aichain_data")

    p.add_argument("--guardian-model", default="")
    p.add_argument("--guardian-threshold", type=float, default=0.7)
    p.add_argument("--guardian-mode", default="quarantine", choices=["deny", "quarantine", "fee-bump", "tag-only"])
    p.add_argument("--guardian-log", default="", help="JSONL log decisions")
    p.add_argument("--quarantine-log", default="", help="JSONL log quarantined tx payloads")

    p.add_argument("--rate-max", type=int, default=15)
    p.add_argument("--rate-window", type=int, default=60)

    p.add_argument("--dynamic-threshold", action="store_true")
    p.add_argument("--dyn-target", type=int, default=2000)
    p.add_argument("--dyn-slope", type=float, default=0.15)

    sp = p.add_subparsers(dest="cmd", required=True)

    s0 = sp.add_parser("init")
    s0.set_defaults(func=cmd_init)

    s1 = sp.add_parser("balance")
    s1.add_argument("addr")
    s1.set_defaults(func=cmd_balance)

    s2 = sp.add_parser("send")
    s2.add_argument("from_addr")
    s2.add_argument("to_addr")
    s2.add_argument("amount", type=int)
    s2.add_argument("--fee", type=int, default=1000)
    s2.add_argument("--memo", default="")
    s2.set_defaults(func=cmd_send)

    s3 = sp.add_parser("mine")
    s3.add_argument("miner_addr")
    s3.set_defaults(func=cmd_mine)

    s4 = sp.add_parser("chain")
    s4.add_argument("--n", type=int, default=20)
    s4.set_defaults(func=cmd_chain)

    s5 = sp.add_parser("quarantine")
    s5.add_argument("--n", type=int, default=20)
    s5.set_defaults(func=cmd_quarantine)

    args = p.parse_args()

    if args.guardian_model:
        ok, msg = install_guardian_patch(
            model_path=args.guardian_model,
            base_threshold=args.guardian_threshold,
            mode=args.guardian_mode,
            json_log_path=(args.guardian_log or None),
            quarantine_path=(args.quarantine_log or None),
            rate_max=args.rate_max,
            rate_window_sec=args.rate_window,
            dynamic_threshold=bool(args.dynamic_threshold),
            dyn_mempool_target=args.dyn_target,
            dyn_slope=args.dyn_slope,
        )
        if not ok:
            raise SystemExit(f"guardian error: {msg}")

    args.func(args)


if __name__ == "__main__":
    main()
