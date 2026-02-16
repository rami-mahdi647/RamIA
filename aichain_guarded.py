#!/usr/bin/env python3
# AIChain Guarded Bridge
# - Does NOT modify aichain.py or aiguardian.py on disk.
# - Applies a runtime patch (monkeypatch) so mempool admission is guarded.
#
# Usage examples:
#   python3 aichain_guarded.py --datadir ./data init
#   python3 aichain_guarded.py --datadir ./data balance genesis
#   python3 aichain_guarded.py --datadir ./data --guardian-model ./guardian_model.json send genesis alice 100000 --fee 1000 --memo "hello"
#   python3 aichain_guarded.py --datadir ./data --guardian-model ./guardian_model.json mine miner1
#
# NOTE: This is still a prototype. The guardian features are heuristic unless trained on your dataset.

import argparse
import json
from typing import Any, Dict, Optional, Tuple

import aichain
import aiguardian


def _tx_to_guardian_dict(tx: "aichain.Transaction") -> Dict[str, Any]:
    """
    Map aichain.Transaction -> the feature schema expected by aiguardian.extract_features().
    We keep it minimal and deterministic.

    aiguardian expects:
      amount, fee, outputs, memo, to_addr, burst_score, timestamp
    """
    amount = float(sum(o.amount for o in tx.vout))
    fee = float(tx.fee)
    outputs = int(len(tx.vout))
    memo = str(tx.memo or "")

    # choose first output as representative destination (toy)
    to_addr = tx.vout[0].to_addr if tx.vout else ""

    return {
        "amount": amount,
        "fee": fee,
        "outputs": outputs,
        "memo": memo,
        "to_addr": to_addr,
        "burst_score": 0.0,              # hook: compute from local history later
        "timestamp": int(aichain.now_ts())
    }


def install_guardian_patch(
    model_path: str,
    threshold: float,
    mode: str = "deny",
    json_log_path: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Patch aichain.ChainDB.add_tx_to_mempool so every tx is scored by Guardian.

    mode:
      - "deny": reject tx if score >= threshold
      - "fee-bump": if score >= threshold, require extra fee (simple policy)
      - "tag-only": never reject, only logs score (for observation)

    json_log_path:
      - if provided, append JSON lines with txid/score/decision.
    """
    if not model_path:
        return False, "guardian model path missing"

    model = aiguardian.LogisticModel.load(model_path)
    guardian = aiguardian.Guardian(model, threshold=threshold)

    original = aichain.ChainDB.add_tx_to_mempool

    def guarded_add_tx_to_mempool(self: "aichain.ChainDB", tx: "aichain.Transaction"):
        # coinbase should never enter mempool; but keep it pass-through
        if len(tx.vin) == 1 and tx.vin[0].from_addr == "COINBASE":
            return original(self, tx)

        tx_dict = _tx_to_guardian_dict(tx)
        score = guardian.score(tx_dict)

        decision = "allow"
        reason = "ok"

        if mode == "deny":
            if score >= threshold:
                decision = "deny"
                reason = "guardian_threshold_exceeded"
                result = (False, f"guardian denied: score={score:.6f} >= {threshold:.6f}")
            else:
                result = original(self, tx)

        elif mode == "fee-bump":
            # Example policy: if score is high, require fee >= base + k*score
            # Keep it simple and deterministic.
            required_fee = int(1000 + (score * 100000))  # tune later
            if tx.fee < required_fee:
                decision = "deny"
                reason = "guardian_fee_bump_required"
                result = (False, f"guardian fee-bump: fee={tx.fee} < required_fee={required_fee} (score={score:.6f})")
            else:
                result = original(self, tx)

        elif mode == "tag-only":
            result = original(self, tx)

        else:
            return (False, f"unknown guardian mode: {mode}")

        # Optional JSONL logging
        if json_log_path:
            try:
                payload = {
                    "ts": int(aichain.now_ts()),
                    "txid": tx.txid(),
                    "score": float(score),
                    "threshold": float(threshold),
                    "mode": mode,
                    "decision": decision,
                    "reason": reason,
                    "fee": int(tx.fee),
                    "amount": int(sum(o.amount for o in tx.vout)),
                    "to": tx.vout[0].to_addr if tx.vout else "",
                }
                with open(json_log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(payload, sort_keys=True) + "\n")
            except Exception:
                pass

        return result

    # install patch
    aichain.ChainDB.add_tx_to_mempool = guarded_add_tx_to_mempool  # type: ignore[attr-defined]
    return True, "guardian patch installed"


# ----------------------------
# CLI commands mirror aichain.py
# ----------------------------

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


def main():
    p = argparse.ArgumentParser(prog="aichain_guarded")

    p.add_argument("--datadir", default="./aichain_data")

    # Guardian controls (optional, but if you provide --guardian-model it patches runtime)
    p.add_argument("--guardian-model", default="", help="Path to guardian_model.json")
    p.add_argument("--guardian-threshold", type=float, default=0.7, help="Deny if score >= threshold")
    p.add_argument("--guardian-mode", default="deny", choices=["deny", "fee-bump", "tag-only"])
    p.add_argument("--guardian-log", default="", help="Optional JSONL log file path (append)")

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

    args = p.parse_args()

    # Apply patch if guardian-model provided
    if args.guardian_model:
        ok, msg = install_guardian_patch(
            model_path=args.guardian_model,
            threshold=args.guardian_threshold,
            mode=args.guardian_mode,
            json_log_path=(args.guardian_log or None),
        )
        if not ok:
            raise SystemExit(f"guardian error: {msg}")

    args.func(args)


if __name__ == "__main__":
    main()
