#!/usr/bin/env python3
"""RamIA local node runner with Stripe grant redemption endpoint.

This is a new entrypoint that extends aicore_plus without modifying existing core modules.
"""

from __future__ import annotations

import argparse
import os
import socketserver
import sys

import aicore_plus
import stripe_bridge


class ExtendedHandler(aicore_plus.LocalHandlerPlus):
    def route(self, path, data):
        if path == "/api/redeem_grant":
            renter = str(data.get("renter", "")).strip()
            token = str(data.get("token", "")).strip()
            if not renter or not token:
                return {"ok": False, "error": "missing_renter_or_token"}
            try:
                payload = stripe_bridge.verify_grant_token(token)
                if payload["renter"] != renter:
                    return {"ok": False, "error": "renter_mismatch"}
                out = stripe_bridge.apply_credit_to_market(self.ctxp.core.market, renter, payload["credits_to_add"])
                self.ctxp.core.audit.append(
                    {
                        "type": "stripe_grant_redeem_v1",
                        "renter": renter,
                        "credits": payload["credits_to_add"],
                        "bots_count": payload["bots_count"],
                        "session_id": payload.get("session_id", "unknown"),
                    }
                )
                self.ctxp.core.save()
                return out
            except Exception as exc:
                return {"ok": False, "error": str(exc)}
        return super().route(path, data)


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


def run_web(ctxp, ui_html: str, host: str, port: int):
    class ThreadingHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True

    ExtendedHandler.ctxp = ctxp
    ExtendedHandler.ui_html = ui_html
    httpd = ThreadingHTTPServer((host, port), ExtendedHandler)
    print(f"[ramia-core-plus] web=http://{host}:{port}")
    print("[ramia-core-plus] endpoint: POST /api/redeem_grant")
    httpd.serve_forever()


def main():
    p = argparse.ArgumentParser(prog="ramia_core_plus")
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
