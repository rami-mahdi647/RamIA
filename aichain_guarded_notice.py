#!/usr/bin/env python3
# AIChain Guarded Notice Bridge
# Runtime patch only. No edits to aichain.py or aiguardian.py
#
# Behavior:
# - On suspicious tx: return a WARNING payload explaining WHY and HOW to reduce penalties.
# - Optionally accept if user passes --accept-risk and fee >= recommended_fee.
#
# Examples:
#   python3 aiguardian.py train --csv dataset.csv --out guardian_model.json
#   python3 aichain_guarded_notice.py --guardian-model guardian_model.json init
#   python3 aichain_guarded_notice.py --guardian-model guardian_model.json send genesis alice 100000 --fee 1000 --memo "hello"
#   python3 aichain_guarded_notice.py --guardian-model guardian_model.json --accept-risk send genesis alice 100000 --fee 200000

import argparse
import json
from typing import Any, Dict, List, Optional, Tuple

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
        "burst_score": 0.0,               # hook: add real history later
        "timestamp": int(aichain.now_ts())
    }


def _reasons_and_advice(tx: "aichain.Transaction", score: float) -> Tuple[List[str], List[str]]:
    """
    Human-readable reasons (heuristic) + actionable advice.
    This is interpretability without needing model internals.
    """
    reasons: List[str] = []
    advice: List[str] = []

    amount = sum(o.amount for o in tx.vout)
    fee = tx.fee
    outputs = len(tx.vout)
    memo_len = len(tx.memo or "")
    to_addr = tx.vout[0].to_addr if tx.vout else ""
    ent = aiguardian.shannon_entropy(to_addr)

    # Heuristic triggers (tune freely)
    if fee <= 0:
        reasons.append("Fee muy baja o nula (patrón típico de spam).")
        advice.append("Sube el fee para priorizar tu transacción y evitar ser marcada como spam.")
    if outputs >= 10:
        reasons.append("Muchos outputs en una sola transacción (patrón de dispersión/splitting).")
        advice.append("Reduce el número de outputs o divide la operación en varias transacciones separadas.")
    if memo_len > 140:
        reasons.append("Memo muy largo (posible payload / abuso de datos en cadena).")
        advice.append("Acorta el memo o evita incluir datos innecesarios en la transacción.")
    if ent >= 3.5 and len(to_addr) >= 12:
        reasons.append("Destino con alta entropía (parece dirección generada/automatizada).")
        advice.append("Si puedes, reutiliza destinos verificados o reduce el número de destinos nuevos por minuto.")
    if amount == 0:
        reasons.append("Importe 0 (patrón clásico de spam/ping).")
        advice.append("Evita transacciones de importe 0; usa un importe mínimo significativo.")
    if score >= 0.9:
        reasons.append("Score muy alto: patrón global similar a spam/abuso.")
        advice.append("Reduce frecuencia de envíos, sube fee y evita patrones repetitivos (mismo memo/destinos).")
    elif score >= 0.7:
        reasons.append("Score alto: podría ser spam o actividad automatizada.")
        advice.append("Baja la frecuencia (rate), sube fee, y evita bursts (ráfagas) de transacciones consecutivas.")
    elif score >= 0.5:
        reasons.append("Score medio: actividad borderline.")
        advice.append("Pequeños ajustes de fee y comportamiento suelen bastar para pasar sin penalización.")

    if not reasons:
        reasons.append("Marcada por política adaptativa (congestión o señales débiles combinadas).")
        advice.append("Sube ligeramente el fee o reduce el ritmo de transacciones.")

    return reasons, advice


def recommended_fee(base_fee: int, score: float, multiplier: int = 100000) -> int:
    """
    Progressive penalty: higher score => higher required fee.
    """
    # base_fee is user's offered fee; we set a recommended fee >= base floor.
    floor = 1000
    rec = int(max(floor, base_fee, floor + score * float(multiplier)))
    return rec


def install_notice_patch(
    model_path: str,
    threshold: float,
    accept_risk: bool,
    log_path: Optional[str] = None,
    penalty_multiplier: int = 100000,
) -> Tuple[bool, str]:
    model = aiguardian.LogisticModel.load(model_path)
    guardian = aiguardian.Guardian(model, threshold=threshold)

    original_add = aichain.ChainDB.add_tx_to_mempool

    def _log(payload: Dict[str, Any]):
        if not log_path:
            return
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, sort_keys=True) + "\n")
        except Exception:
            pass

    def guarded_add(self: "aichain.ChainDB", tx: "aichain.Transaction"):
        # Pass-through coinbase
        if len(tx.vin) == 1 and tx.vin[0].from_addr == "COINBASE":
            return original_add(self, tx)

        tx_dict = _tx_to_guardian_dict(tx)
        score = guardian.score(tx_dict)

        if score < threshold:
            # allow
            res = original_add(self, tx)
            payload = {
                "ts": int(aichain.now_ts()),
                "txid": tx.txid(),
                "sender": _tx_sender(tx),
                "decision": "allow",
                "score": float(score),
                "threshold": float(threshold),
            }
            _log(payload)
            return res

        # suspicious => warn, compute fee recommendation and advice
        reasons, advice = _reasons_and_advice(tx, score)
        rec_fee = recommended_fee(tx.fee, score, multiplier=penalty_multiplier)

        warning = {
            "allow": False,
            "warning": True,
            "txid": tx.txid(),
            "score": float(score),
            "threshold": float(threshold),
            "message": "Transacción sospechosa",
            "reasons": reasons,
            "recommendations": {
                "recommended_fee": int(rec_fee),
                "your_fee": int(tx.fee),
                "how_to_reduce_fee": advice,
            },
            "next_steps": [
                "Ajusta el fee al recomendado o superior",
                "Reduce el ritmo (evita ráfagas de transacciones)",
                "Evita memos largos y patrones repetitivos",
            ],
        }

        payload = {
            "ts": int(aichain.now_ts()),
            "txid": tx.txid(),
            "sender": _tx_sender(tx),
            "decision": "warn",
            "score": float(score),
            "threshold": float(threshold),
            "recommended_fee": int(rec_fee),
            "reasons": reasons,
        }
        _log(payload)

        if accept_risk:
            if tx.fee >= rec_fee:
                # user explicitly accepts and pays penalty => allow
                payload2 = dict(payload)
                payload2["decision"] = "allow_after_warning"
                _log(payload2)
                return original_add(self, tx)

            # accept-risk but fee insufficient: still block with clear notice
            warning["next_steps"].insert(0, "Has activado --accept-risk, pero tu fee no llega al mínimo recomendado.")
            return (False, json.dumps(warning, ensure_ascii=False))

        # default: do not admit to mempool
        return (False, json.dumps(warning, ensure_ascii=False))

    aichain.ChainDB.add_tx_to_mempool = guarded_add  # type: ignore[attr-defined]
    return True, "notice patch installed"


# --- CLI mirrors aichain, plus flags ---

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
        # If it's a JSON warning, pretty-print it.
        try:
            obj = json.loads(out)
            print(json.dumps(obj, indent=2, ensure_ascii=False))
        except Exception:
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
    p = argparse.ArgumentParser(prog="aichain_guarded_notice")
    p.add_argument("--datadir", default="./aichain_data")

    p.add_argument("--guardian-model", required=True)
    p.add_argument("--threshold", type=float, default=0.7)
    p.add_argument("--accept-risk", action="store_true", help="Allow suspicious tx only if fee >= recommended_fee")
    p.add_argument("--log", default="", help="Optional JSONL log file")
    p.add_argument("--penalty-multiplier", type=int, default=100000)

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

    ok, msg = install_notice_patch(
        model_path=args.guardian_model,
        threshold=args.threshold,
        accept_risk=bool(args.accept_risk),
        log_path=(args.log or None),
        penalty_multiplier=args.penalty_multiplier,
    )
    if not ok:
        raise SystemExit(msg)

    args.func(args)


if __name__ == "__main__":
    main()
