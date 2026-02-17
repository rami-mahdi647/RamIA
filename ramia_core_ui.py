#!/usr/bin/env python3
"""RamIA UI adapter layer with guardian explain endpoint."""

from __future__ import annotations

import argparse
import os
import socketserver
import sys
import time
from typing import Any, Dict, List

import aicore_plus
import aiguardian


def parse_conf(path: str):
    cfg = {}
    if not os.path.exists(path):
        return cfg
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    return cfg


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _deterministic_suggestions() -> List[str]:
    return [
        "Reduce the number of outputs to keep the transfer pattern simple.",
        "Adjust the memo to short, plain text without unusual symbols.",
        "Increase the fee to better match current policy expectations.",
        "Slow down burst rate by spacing transactions over time.",
    ]


def _memo_anomaly_score(memo: str) -> float:
    if not memo:
        return 0.25
    weird = sum(1 for ch in memo if not (32 <= ord(ch) <= 126))
    symbolish = sum(1 for ch in memo if not ch.isalnum() and not ch.isspace())
    length_factor = 0.4 if len(memo) > 64 else 0.0
    return _clamp((weird / max(1, len(memo))) + (symbolish / max(1, len(memo))) + length_factor, 0.0, 1.0)


def build_guardian_explain(data: Dict[str, Any], model_path: str | None) -> Dict[str, Any]:
    amount = int(data.get("amount", 0) or 0)
    fee = int(data.get("fee", 0) or 0)
    memo = str(data.get("memo", "") or "")
    to_addr = str(data.get("to_addr", "") or "")
    outputs = int(data.get("outputs", 1) or 1)
    burst_score = float(data.get("burst_score", 0.0) or 0.0)
    ts = int(data.get("timestamp", int(time.time())) or int(time.time()))

    entropy = aiguardian.shannon_entropy(to_addr)
    memo_score = _memo_anomaly_score(memo)

    baseline_fee = max(1000, int(amount * 0.0015) + int(outputs * 500) + int(max(0.0, burst_score) * 350))
    fee_multiplier = round(max(1.0, baseline_fee / max(1, fee)), 3)

    heuristic_risk = _clamp(
        0.18
        + (0.22 if burst_score >= 1.5 else burst_score * 0.12)
        + (0.16 if outputs >= 4 else outputs * 0.03)
        + memo_score * 0.2
        + (0.16 if fee < baseline_fee else 0.0)
        + (0.10 if entropy >= 3.6 else 0.0),
        0.0,
        0.99,
    )

    model_risk = None
    if model_path and os.path.exists(model_path):
        try:
            model = aiguardian.LogisticModel.load(model_path)
            guardian = aiguardian.Guardian(model, threshold=0.7)
            txd = {
                "amount": amount,
                "fee": fee,
                "outputs": outputs,
                "memo": memo,
                "to_addr": to_addr,
                "burst_score": burst_score,
                "timestamp": ts,
            }
            model_risk = float(guardian.score(txd))
        except Exception:
            model_risk = None

    risk_score = round(model_risk if model_risk is not None else heuristic_risk, 4)

    reasons: List[str] = []
    if burst_score >= 1.0:
        reasons.append("Recent sending pattern looks bursty, which can increase temporary risk controls.")
    if outputs >= 3 or entropy >= 3.8:
        reasons.append("Output pattern appears complex, so it may look less like a routine single-recipient payment.")
    if memo_score >= 0.35:
        reasons.append("Memo has unusual structure or length and may be interpreted as anomalous metadata.")
    if fee < baseline_fee:
        reasons.append("Offered fee is below the current policy estimate for this transaction profile.")

    if not reasons:
        reasons.append("Transaction profile is generally healthy with no major policy mismatch detected.")
    reasons = reasons[:4]

    suggestions = _deterministic_suggestions()
    if fee >= baseline_fee:
        suggestions = [s for s in suggestions if not s.startswith("Increase the fee")]
        suggestions.insert(0, "Keep the current fee level and maintain simple outputs for stable acceptance.")
    suggestions = suggestions[:4]

    return {
        "ok": True,
        "risk_score": risk_score,
        "reasons": reasons[:4],
        "suggestions": suggestions[:4],
        "fee_multiplier": fee_multiplier,
    }


class UIAdapterHandler(aicore_plus.LocalHandlerPlus):
    def route(self, path, data):
        if path == "/api/guardian_explain":
            model_path = getattr(self.ctxp.core.args, "guardian_model", None)
            return build_guardian_explain(data, model_path)
        return super().route(path, data)


def run_web(ctxp, ui_html: str, host: str, port: int):
    class ThreadingHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True

    UIAdapterHandler.ctxp = ctxp
    UIAdapterHandler.ui_html = ui_html
    httpd = ThreadingHTTPServer((host, port), UIAdapterHandler)
    print(f"[ramia-core-ui] web=http://{host}:{port}")
    print("[ramia-core-ui] endpoint: POST /api/guardian_explain")
    httpd.serve_forever()


def main():
    p = argparse.ArgumentParser(prog="ramia_core_ui")
    p.add_argument("--conf", default="./ramia.conf")
    p.add_argument("--guardian-model", default=None)
    p.add_argument("--datadir", default=None)
    p.add_argument("--web", action="store_true")
    p.add_argument("--no-web", action="store_true")
    p.add_argument("--web-port", type=int, default=None)
    p.add_argument("--web-host", default=None)
    args = p.parse_args()

    cfg = parse_conf(args.conf)
    core_args = argparse.Namespace(
        datadir=args.datadir or cfg.get("datadir") or "./aichain_data",
        guardian_model=args.guardian_model or cfg.get("guardian_model") or "./guardian_model.json",
        threshold=float(cfg.get("threshold", "0.70")),
        privacy_mode=cfg.get("privacy_mode", "receipt_only"),
        fleet_state=cfg.get("fleet_state", "./fleet_state.json"),
        fleet_size=int(cfg.get("fleet_size", "2000")),
        fleet_seed=int(cfg.get("fleet_seed", "1337")),
        committee_size=int(cfg.get("committee_size", "11")),
        burst_state=cfg.get("burst_state", "./burst_state.json"),
        burst_window=int(cfg.get("burst_window", "60")),
        burst_max=int(cfg.get("burst_max", "10")),
        market_state=cfg.get("market_state", "./market_secure_state.bin"),
        secret_file=cfg.get("secret_file", "./market_secret.key"),
        audit_log=cfg.get("audit_log", "./audit_log.jsonl"),
    )

    ctxp = aicore_plus.AppContextPlus(core_args, wallet_file=cfg.get("wallet_file", "./wallet.json"))
    ui_file = cfg.get("ui_file", "./ui_plus.html")
    if not os.path.exists(ui_file):
        print(f"[fatal] ui file not found: {ui_file}", file=sys.stderr)
        sys.exit(2)

    html = aicore_plus.load_ui_html(ui_file)
    web_enabled = cfg.get("web", "1") in ("1", "true", "yes", "on")
    if args.web:
        web_enabled = True
    if args.no_web:
        web_enabled = False
    if not web_enabled:
        print("[node] web disabled by config.")
        return

    run_web(ctxp, html, args.web_host or cfg.get("web_host", "127.0.0.1"), args.web_port or int(cfg.get("web_port", "8787")))


if __name__ == "__main__":
    main()
