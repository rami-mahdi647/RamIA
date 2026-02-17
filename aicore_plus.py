#!/usr/bin/env python3
# AIChain Core+ (extension) — adds Wallet + Founder Mode + Improved UI
# WITHOUT modifying aicore.py

import argparse
import json
import os
import secrets
import hashlib
import stat
import socketserver
from http.server import BaseHTTPRequestHandler
from typing import Any, Dict, Tuple

import aicore  # your existing file

# Optional real keys if cryptography exists
try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # type: ignore
    from cryptography.hazmat.primitives import serialization  # type: ignore
    HAVE_CRYPTO_REAL = True
except Exception:
    HAVE_CRYPTO_REAL = False


# -------------------------
# Small helpers
# -------------------------

def ensure_dir(path: str):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)

def chmod_600_best_effort(path: str):
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass

def jdump(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")

def b64e(b: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(b).decode("utf-8").rstrip("=")

def b64d(s: str) -> bytes:
    import base64
    pad = "=" * ((4 - (len(s) % 4)) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("utf-8"))


# -------------------------
# Wallet Manager (new)
# -------------------------

class WalletManager:
    """
    Stores wallet locally (wallet.json):
      - If cryptography available: Ed25519 (real keys)
      - Else: DEV fallback (not production crypto)
    Address = sha256(public_key_bytes)[:40]
    """
    def __init__(self, wallet_file: str):
        self.wallet_file = wallet_file

    def exists(self) -> bool:
        return os.path.exists(self.wallet_file)

    def _address_from_pub(self, pub: bytes) -> str:
        return hashlib.sha256(pub).hexdigest()[:40]

    def create(self, label: str = "default") -> Dict[str, Any]:
        ensure_dir(self.wallet_file)

        if HAVE_CRYPTO_REAL:
            sk = Ed25519PrivateKey.generate()
            pk = sk.public_key()
            sk_bytes = sk.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption(),
            )
            pk_bytes = pk.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            addr = self._address_from_pub(pk_bytes)
            obj = {
                "version": 1,
                "type": "ed25519",
                "label": label,
                "address": addr,
                "public_key": b64e(pk_bytes),
                "private_key": b64e(sk_bytes),
                "note": "Back up this file. Keep private_key secret.",
            }
        else:
            priv = secrets.token_bytes(32)
            pub = hashlib.sha256(priv).digest()
            addr = self._address_from_pub(pub)
            obj = {
                "version": 1,
                "type": "dev_wallet",
                "label": label,
                "address": addr,
                "public_key": b64e(pub),
                "private_key": b64e(priv),
                "note": "DEV wallet (install cryptography for Ed25519 real keys).",
            }

        tmp = self.wallet_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False, indent=2))
        os.replace(tmp, self.wallet_file)
        chmod_600_best_effort(self.wallet_file)
        return obj

    def load(self) -> Dict[str, Any]:
        with open(self.wallet_file, "r", encoding="utf-8") as f:
            return json.loads(f.read())

    def info(self) -> Dict[str, Any]:
        if not self.exists():
            return {"ok": False, "error": "no_wallet"}
        w = self.load()
        return {
            "ok": True,
            "wallet_file": self.wallet_file,
            "type": w.get("type"),
            "label": w.get("label"),
            "address": w.get("address"),
            "security_note": ("Ed25519 real keys" if w.get("type") == "ed25519" else "DEV wallet (install cryptography)"),
        }

    def address(self) -> str:
        return str(self.load().get("address", ""))


# -------------------------
# UI loader (new file)
# -------------------------

def load_ui_html(ui_file: str) -> str:
    with open(ui_file, "r", encoding="utf-8") as f:
        return f.read()


# -------------------------
# Extended Web Handler
# -------------------------

class AppContextPlus:
    """
    Wraps aichain core context + adds wallet manager.
    """
    def __init__(self, core_args: argparse.Namespace, wallet_file: str):
        self.core = aicore.AppContext(core_args)   # reuse everything from aicore.py
        self.wallet = WalletManager(wallet_file)

    def db(self):
        return self.core.db()

    def save(self):
        self.core.save()


class LocalHandlerPlus(BaseHTTPRequestHandler):
    ctxp: AppContextPlus = None  # injected
    ui_html: str = ""

    def _send(self, status: int, ctype: str, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(200, "text/html; charset=utf-8", self.ui_html.encode("utf-8"))
            return
        self._send(404, "text/plain; charset=utf-8", b"not found")

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            data = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            self._send(400, "application/json; charset=utf-8", jdump({"ok": False, "error": "bad_json"}))
            return

        try:
            out = self.route(self.path, data)
            self._send(200, "application/json; charset=utf-8", jdump(out))
        except Exception as e:
            self._send(500, "application/json; charset=utf-8", jdump({"ok": False, "error": "internal_error", "detail": str(e)}))

    def route(self, path: str, data: Dict[str, Any]) -> Dict[str, Any]:
        ctxp = self.ctxp
        core = ctxp.core

        # ---- New endpoints (wallet + founder) ----

        if path == "/api/wallet_create":
            label = str(data.get("label", "default"))
            if ctxp.wallet.exists():
                return {"ok": False, "error": "wallet_exists", "wallet_file": ctxp.wallet.wallet_file}
            w = ctxp.wallet.create(label=label)
            return {"ok": True, "wallet": {"address": w["address"], "type": w["type"]}, "wallet_file": ctxp.wallet.wallet_file}

        if path == "/api/wallet_info":
            return ctxp.wallet.info()

        if path == "/api/founder_enable":
            # Ensure wallet exists
            if not ctxp.wallet.exists():
                ctxp.wallet.create(label="founder")
            founder_addr = ctxp.wallet.address()

            # Create founder renter if missing
            founder_renter = "FOUNDER"
            founder_api_key_dev = None
            if founder_renter not in core.market.state["renters"]:
                out = core.market.renter_create(founder_renter)
                founder_api_key_dev = out.get("api_key")

            # Reserve "10k bots fixed" concept:
            # Implemented as: permanent Platinum reserved contract + massive credits
            cid = core.market.reserved_create(
                renter=founder_renter,
                tier="Platinum",
                renters_pool_bps=9000,
                duration_sec=365 * 24 * 3600,
                credits=10_000_000,
            )

            core.audit.append({
                "type": "founder_enable",
                "founder_address": founder_addr,
                "founder_renter": founder_renter,
                "contract_id": cid,
                "bots_fixed_claim": 10000,
            })
            core.save()
            return {
                "ok": True,
                "founder_address": founder_addr,
                "founder_renter": founder_renter,
                "reserved_contract_id": cid,
                "bots_fixed": 10000,
                "note": "Founder mode enabled (concept: permanent reserved priority + credits).",
                # dev convenience (optional):
                "founder_api_key_dev": founder_api_key_dev,
            }

        # ---- Delegate to original aicore routes for everything else ----
        # We reuse the same behavior by calling aicore.LocalHandler.route logic,
        # but without instantiating it. So we copy the minimal endpoints we need:
        # Instead: call core operations directly here for common actions:

        if path == "/api/status":
            db = core.db()
            w = ctxp.wallet.info()
            return {
                "ok": True,
                "height": db.height(),
                "tip": db.tip().block_hash(),
                "mempool": len(db.mempool),
                "wallet": w,
                "security": {
                    "encrypted_state": bool(core.sec.fernet is not None),
                    "audit_log": core.args.audit_log,
                }
            }

        if path == "/api/init":
            db = core.db()
            return {"ok": True, "height": db.height(), "tip": db.tip().block_hash()}

        if path == "/api/mine":
            db = core.db()
            tpl = db.build_block_template(str(data.get("any_miner_addr", "x")))
            blk = db._mine_block(tpl)
            ok, why = db.submit_block(blk)
            core.save()
            if not ok:
                return {"ok": False, "error": why}
            return {
                "ok": True,
                "height": db.height(),
                "hash": blk.block_hash(),
                "coinbase_to": blk.txs[0].vout[0].to_addr if blk.txs and blk.txs[0].vout else "",
                "coinbase_paid": sum(o.amount for o in blk.txs[0].vout) if blk.txs and blk.txs[0].vout else 0,
            }

        if path == "/api/send":
            db = core.db()
            tx = db.make_tx(
                str(data.get("from_addr", "")),
                str(data.get("to_addr", "")),
                int(data.get("amount", 0)),
                int(data.get("fee", 1000)),
                memo=str(data.get("memo", "")),
            )
            ok, out = db.add_tx_to_mempool(tx)
            core.save()
            if ok:
                return {"ok": True, "txid": out}
            try:
                return {"ok": False, "result": json.loads(out)}
            except Exception:
                return {"ok": False, "result": out}

        if path == "/api/audit_verify":
            return core.audit.verify()

        # Marketplace basic (reuse core ones)
        if path == "/api/renter_create":
            renter = str(data.get("renter", ""))
            if not renter:
                return {"ok": False, "error": "missing_renter"}
            out = core.market.renter_create(renter)
            core.save()
            out["security_note"] = ("encrypted_state+HMAC" if core.sec.fernet else "HMAC_only (install cryptography for encryption)")
            return out

        if path == "/api/renter_status":
            renter = str(data.get("renter", ""))
            api_key = str(data.get("api_key", ""))
            payload = core.signed_payload(renter, "renter_status", {"action": "renter_status"})
            ok, reason = core.require_market_auth(renter, api_key, "renter_status", payload)
            if not ok:
                return {"ok": False, "error": reason}
            return {
                "ok": True,
                "renter": renter,
                "balance": int(core.market.state["balances"].get(renter, 0)),
                "credits": int(core.market.state["credits"].get(renter, 0)),
                "active_orders": [
                    {"order_id": oid, **o}
                    for oid, o in core.market.state["orders"].items()
                    if o.get("renter") == renter and o.get("active")
                ],
                "active_reserved": [
                    {"contract_id": cid, **c}
                    for cid, c in core.market.state["reserved"].items()
                    if c.get("renter") == renter and int(c.get("expires_ts", 0)) > int(aicore.now_ts())
                ]
            }

        if path == "/api/order_place":
            renter = str(data.get("renter", ""))
            api_key = str(data.get("api_key", ""))
            tier = str(data.get("tier", "Gold"))
            bid_bps = int(data.get("bid_bps", 7000))
            max_credits = int(data.get("max_credits", 1000))
            payload = core.signed_payload(renter, "order_place", {"tier": tier, "bid_bps": bid_bps, "max_credits": max_credits})
            ok, reason = core.require_market_auth(renter, api_key, "order_place", payload)
            if not ok:
                return {"ok": False, "error": reason}
            if tier not in aicore.TIERS:
                return {"ok": False, "error": "bad_tier"}
            oid = core.market.order_place(renter, tier, bid_bps, max_credits)
            core.audit.append({"type": "api_order_place", "renter": renter, "tier": tier, "oid": oid})
            core.save()
            return {"ok": True, "order_id": oid}

        if path == "/api/reserved_create":
            renter = str(data.get("renter", ""))
            api_key = str(data.get("api_key", ""))
            tier = str(data.get("tier", "Gold"))
            renters_pool_bps = int(data.get("renters_pool_bps", 6500))
            duration_sec = int(data.get("duration_sec", 3600))
            credits = int(data.get("credits", 5000))
            payload = core.signed_payload(renter, "reserved_create", {
                "tier": tier, "renters_pool_bps": renters_pool_bps, "duration_sec": duration_sec, "credits": credits
            })
            ok, reason = core.require_market_auth(renter, api_key, "reserved_create", payload)
            if not ok:
                return {"ok": False, "error": reason}
            if tier not in aicore.TIERS:
                return {"ok": False, "error": "bad_tier"}
            cid = core.market.reserved_create(renter, tier, renters_pool_bps, duration_sec, credits)
            core.audit.append({"type": "api_reserved_create", "renter": renter, "tier": tier, "cid": cid})
            core.save()
            return {"ok": True, "contract_id": cid}

        return {"ok": False, "error": "unknown_endpoint"}


def run_web_plus(ctxp: AppContextPlus, ui_html: str, host: str, port: int):
    class ThreadingHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True

    LocalHandlerPlus.ctxp = ctxp
    LocalHandlerPlus.ui_html = ui_html
    httpd = ThreadingHTTPServer((host, port), LocalHandlerPlus)
    print(f"[web+] http://{host}:{port}")
    httpd.serve_forever()


def main():
    p = argparse.ArgumentParser(prog="aicore_plus")

    # Core args (same as aicore.py)
    p.add_argument("--datadir", default="./aichain_data")
    p.add_argument("--guardian-model", required=True)
    p.add_argument("--threshold", type=float, default=0.7)
    p.add_argument("--privacy-mode", default="receipt_only", choices=["receipt_only", "reveal_to_sender"])

    p.add_argument("--fleet-state", default="./fleet_state.json")
    p.add_argument("--fleet-size", type=int, default=100000)
    p.add_argument("--fleet-seed", type=int, default=1337)
    p.add_argument("--committee-size", type=int, default=21)

    p.add_argument("--burst-state", default="./burst_state.json")
    p.add_argument("--burst-window", type=int, default=60)
    p.add_argument("--burst-max", type=int, default=10)

    p.add_argument("--market-state", default="./market_secure_state.bin")
    p.add_argument("--secret-file", default="./market_secret.key")
    p.add_argument("--audit-log", default="./audit_log.jsonl")

    # New args (plus)
    p.add_argument("--wallet-file", default="./wallet.json")
    p.add_argument("--ui-file", default="./ui_plus.html")

    sp = p.add_subparsers(dest="cmd", required=True)

    node = sp.add_parser("node")
    node.add_argument("--web-host", default="127.0.0.1")
    node.add_argument("--web-port", type=int, default=8787)
    node.set_defaults(mode="node")

    args = p.parse_args()

    # Build a Namespace for core (AppContext expects .args etc)
    core_args = argparse.Namespace(**{
        "datadir": args.datadir,
        "guardian_model": args.guardian_model,
        "threshold": args.threshold,
        "privacy_mode": args.privacy_mode,
        "fleet_state": args.fleet_state,
        "fleet_size": args.fleet_size,
        "fleet_seed": args.fleet_seed,
        "committee_size": args.committee_size,
        "burst_state": args.burst_state,
        "burst_window": args.burst_window,
        "burst_max": args.burst_max,
        "market_state": args.market_state,
        "secret_file": args.secret_file,
        "audit_log": args.audit_log,
    })

    ctxp = AppContextPlus(core_args, wallet_file=args.wallet_file)
    ui_html = load_ui_html(args.ui_file)

    if args.cmd == "node":
        run_web_plus(ctxp, ui_html, args.web_host, args.web_port)


if __name__ == "__main__":
    main()
