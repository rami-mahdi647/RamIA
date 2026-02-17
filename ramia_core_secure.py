#!/usr/bin/env python3
 codex/clean-up-code-and-remove-duplicates
"""RamIA secure production entrypoint with replay-safe Stripe grant redemption."""

import argparse
import os
import socketserver
import sys

import aicore_plus
import stripe_bridge
=======
"""RamIA secure entrypoint with signed transaction enforcement."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import socketserver
import sys
from http.server import BaseHTTPRequestHandler
from typing import Any, Dict, Tuple

import aichain
import aicore_plus
import crypto_backend
 main


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


def as_int(cfg, k, default):
    try:
        return int(cfg.get(k, default))
    except Exception:
        return default


def as_float(cfg, k, default):
    try:
        return float(cfg.get(k, default))
    except Exception:
        return default


def as_bool(cfg, k, default):
    v = str(cfg.get(k, "1" if default else "0")).lower()
    return v in ("1", "true", "yes", "on")


 codex/clean-up-code-and-remove-duplicates
class ExtendedHandler(aicore_plus.LocalHandlerPlus):
    def route(self, path, data):
        if path == "/api/redeem_grant":
            renter = str(data.get("renter", "")).strip()
            token = str(data.get("token", "")).strip()
            if not renter or not token:
                return {"ok": False, "error": "missing_renter_or_token"}
            _, out = stripe_bridge.redeem_grant_token(self.ctxp, token, expected_renter=renter)
            return out

        if path == "/api/redeem_grant_token":
            token = str(data.get("grant_token", "")).strip()
            _, out = stripe_bridge.redeem_grant_token(self.ctxp, token)
            return out

def canonical_signing_payload(tx: aichain.Transaction) -> bytes:
    payload = {
        "version": tx.version,
        "vin": [{"from_addr": i.from_addr} for i in tx.vin],
        "vout": [{"to_addr": o.to_addr, "amount": o.amount} for o in tx.vout],
        "fee": tx.fee,
        "nonce": tx.nonce,
        "memo": tx.memo,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


class SecureChainAdapter:
    """Wraps ChainDB tx creation + mempool admission for signature enforcement."""

    def __init__(self, db: aichain.ChainDB, wallet: Dict[str, Any]):
        self._db = db
        self._wallet = wallet
        self._wallet_address = str(wallet.get("address", ""))

    def __getattr__(self, name: str):
        return getattr(self._db, name)

    def _wallet_pk(self) -> str:
        return str(self._wallet.get("public_key", ""))

    def _wallet_sk(self) -> str:
        return str(self._wallet.get("private_key", ""))

    def _with_sig(self, tx: aichain.Transaction) -> aichain.Transaction:
        payload = canonical_signing_payload(tx)
        sig = crypto_backend.sign(self._wallet_sk(), payload)
        vin = [dataclasses.replace(i, sig=sig) for i in tx.vin]
        return dataclasses.replace(tx, vin=vin)

    def verify_tx_signature(self, tx: aichain.Transaction) -> Tuple[bool, str]:
        if not tx.vin:
            return False, "missing_vin"
        sender = tx.vin[0].from_addr
        if sender != self._wallet_address:
            return False, "unknown_sender_for_secure_mode"
        sig = tx.vin[0].sig
        if not sig:
            return False, "missing_signature"
        ok = crypto_backend.verify(self._wallet_pk(), canonical_signing_payload(tx), sig)
        if not ok:
            return False, "invalid_signature"
        return True, "ok"

    def make_tx(self, from_addr: str, to_addr: str, amount: int, fee: int, memo: str = "") -> aichain.Transaction:
        if from_addr and from_addr != self._wallet_address:
            raise ValueError("from_addr_must_match_wallet")
        tx = self._db.make_tx(self._wallet_address, to_addr, amount, fee, memo=memo)
        return self._with_sig(tx)

    def add_tx_to_mempool(self, tx: aichain.Transaction) -> Tuple[bool, str]:
        ok, why = self.verify_tx_signature(tx)
        if not ok:
            return False, why
        return self._db.add_tx_to_mempool(tx)


class SecureHandler(aicore_plus.LocalHandlerPlus):
    def route(self, path: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if path == "/api/send":
            if not self.ctxp.wallet.exists():
                return {"ok": False, "error": "wallet_missing"}
            wallet = self.ctxp.wallet.load()
            db = SecureChainAdapter(self.ctxp.core.db(), wallet)

            to_addr = str(data.get("to_addr", ""))
            amount = int(data.get("amount", 0))
            fee = int(data.get("fee", 1000))
            memo = str(data.get("memo", ""))
            from_addr = str(data.get("from_addr", wallet.get("address", "")))

            try:
                tx = db.make_tx(from_addr, to_addr, amount, fee, memo=memo)
            except ValueError as exc:
                return {"ok": False, "error": str(exc)}

            ok, out = db.add_tx_to_mempool(tx)
            self.ctxp.core.save()
            if ok:
                return {"ok": True, "txid": out, "signed": True, "from_addr": wallet.get("address", "")}
            return {"ok": False, "error": out}
 main

        return super().route(path, data)


 codex/clean-up-code-and-remove-duplicates
def run_web_with_stripe(ctxp: aicore_plus.AppContextPlus, ui_html: str, host: str, port: int):
    class ThreadingHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True

    ExtendedHandler.ctxp = ctxp
    ExtendedHandler.ui_html = ui_html
    httpd = ThreadingHTTPServer((host, port), ExtendedHandler)
    print(f"[ramia-core-secure] web=http://{host}:{port}")
    print("[ramia-core-secure] endpoints: POST /api/redeem_grant, /api/redeem_grant_token")

def run_secure_web(ctxp: aicore_plus.AppContextPlus, ui_html: str, host: str, port: int):
    class ThreadingHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True

    SecureHandler.ctxp = ctxp
    SecureHandler.ui_html = ui_html
    httpd = ThreadingHTTPServer((host, port), SecureHandler)
    print(f"[ramia-secure] web=http://{host}:{port}")
    print("[ramia-secure] secure mode: signatures required for mempool admission")
 main
    httpd.serve_forever()


def main():
    p = argparse.ArgumentParser(prog="ramia-core-secure")
    p.add_argument("--conf", default="./ramia.conf", help="path to config file")
    p.add_argument("--guardian-model", default=None)
    p.add_argument("--datadir", default=None)
    p.add_argument("--web", action="store_true")
    p.add_argument("--no-web", action="store_true")
    p.add_argument("--web-port", type=int, default=None)
    p.add_argument("--web-host", default=None)
    args = p.parse_args()

    cfg = parse_conf(args.conf)
    guardian_model = args.guardian_model or cfg.get("guardian_model") or "./guardian_model.json"
    datadir = args.datadir or cfg.get("datadir") or "./aichain_data"
    threshold = as_float(cfg, "threshold", 0.70)
    privacy_mode = cfg.get("privacy_mode", "receipt_only")

    fleet_size = as_int(cfg, "fleet_size", 2000)
    committee_size = as_int(cfg, "committee_size", 11)
    fleet_seed = as_int(cfg, "fleet_seed", 1337)

    wallet_file = cfg.get("wallet_file", "./wallet.json")
    ui_file = cfg.get("ui_file", "./ui_plus.html")

    web_enabled = as_bool(cfg, "web", True)
    if args.web:
        web_enabled = True
    if args.no_web:
        web_enabled = False
    web_host = args.web_host or cfg.get("web_host", "127.0.0.1")
    web_port = args.web_port or as_int(cfg, "web_port", 8787)

    core_args = argparse.Namespace(
        datadir=datadir,
        guardian_model=guardian_model,
        threshold=threshold,
        privacy_mode=privacy_mode,
        fleet_state=cfg.get("fleet_state", "./fleet_state.json"),
        fleet_size=fleet_size,
        fleet_seed=fleet_seed,
        committee_size=committee_size,
        burst_state=cfg.get("burst_state", "./burst_state.json"),
        burst_window=as_int(cfg, "burst_window", 60),
        burst_max=as_int(cfg, "burst_max", 10),
        market_state=cfg.get("market_state", "./market_secure_state.bin"),
        secret_file=cfg.get("secret_file", "./market_secret.key"),
        audit_log=cfg.get("audit_log", "./audit_log.jsonl"),
    )

    ctxp = aicore_plus.AppContextPlus(core_args, wallet_file=wallet_file)

    if not os.path.exists(ui_file):
        print(f"[fatal] ui file not found: {ui_file}", file=sys.stderr)
        sys.exit(2)

    html = aicore_plus.load_ui_html(ui_file)
    if not web_enabled:
        print("[node] web disabled by config.")
        sys.exit(0)

 codex/clean-up-code-and-remove-duplicates
    run_web_with_stripe(ctxp, html, web_host, web_port)

    run_secure_web(ctxp, html, web_host, web_port)
 main


if __name__ == "__main__":
    main()
