#!/usr/bin/env python3
 codex/add-post-/api/guardian_explain-endpoint
"""RamIA UI adapter layer with guardian explain endpoint."""

"""RamIA Core UI entrypoint.

Serves Core dashboard static assets and forwards key API routes to existing
core handlers, while adding read-only adapter endpoints.
"""
 main

from __future__ import annotations

import argparse
 codex/add-post-/api/guardian_explain-endpoint
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

import json
import mimetypes
import os
import socketserver
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import aicore_plus


def _json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


class ReadOnlyChainAdapter:
    """Read-only chain projections with file-based fallback."""

    def __init__(self, datadir: str, db: Any):
        self.datadir = Path(datadir)
        self.db = db

    @property
    def _state_path(self) -> Path:
        return self.datadir / "state.json"

    @property
    def _blocks_path(self) -> Path:
        return self.datadir / "blocks.jsonl"

    def _load_state_balances(self) -> Dict[str, int]:
        if not self._state_path.exists():
            return {}
        try:
            with self._state_path.open("r", encoding="utf-8") as f:
                state = json.load(f)
            return {k: int(v) for k, v in state.get("balances", {}).items()}
        except Exception:
            return {}

    def _load_blocks(self) -> List[Dict[str, Any]]:
        if not self._blocks_path.exists():
            return []
        out: List[Dict[str, Any]] = []
        try:
            with self._blocks_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except Exception:
                        continue
        except Exception:
            return []
        return out

    def balance(self, addr: str) -> int:
        balances = getattr(self.db, "balances", None)
        if isinstance(balances, dict):
            try:
                return int(balances.get(addr, 0))
            except Exception:
                pass
        return int(self._load_state_balances().get(addr, 0))

    def mempool_list(self) -> List[Dict[str, Any]]:
        mempool = getattr(self.db, "mempool", None)
        if isinstance(mempool, dict):
            rows: List[Dict[str, Any]] = []
            for txid, tx in mempool.items():
                if hasattr(tx, "to_dict"):
                    obj = tx.to_dict()
                else:
                    obj = {"txid": txid}
                obj.setdefault("txid", txid)
                rows.append(obj)
            return rows
        return []

    def tx_list(self, limit: int = 50) -> List[Dict[str, Any]]:
        # Prefer in-memory chain view
        blocks = getattr(self.db, "blocks", None)
        txs: List[Dict[str, Any]] = []
        if isinstance(blocks, list):
            for blk in reversed(blocks):
                bh = blk.block_hash() if hasattr(blk, "block_hash") else ""
                height = getattr(getattr(blk, "header", None), "height", None)
                for tx in reversed(getattr(blk, "txs", [])):
                    if hasattr(tx, "to_dict"):
                        obj = tx.to_dict()
                    else:
                        obj = {}
                    obj.setdefault("txid", tx.txid() if hasattr(tx, "txid") else "")
                    obj["block_hash"] = bh
                    obj["height"] = height
                    txs.append(obj)
                    if len(txs) >= limit:
                        return txs
            return txs

        # Fallback to persisted jsonl
        file_blocks = self._load_blocks()
        for blk in reversed(file_blocks):
            header = blk.get("header", {})
            tx_arr = blk.get("txs", [])
            for tx in reversed(tx_arr):
                txs.append(
                    {
                        **tx,
                        "txid": tx.get("txid") or "",
                        "height": header.get("height"),
                        "block_hash": "",
                    }
                )
                if len(txs) >= limit:
                    return txs
        return txs

    def blocks_latest(self, limit: int = 10) -> List[Dict[str, Any]]:
        blocks = getattr(self.db, "blocks", None)
        if isinstance(blocks, list):
            out: List[Dict[str, Any]] = []
            for blk in reversed(blocks[-max(1, limit):]):
                hdr = getattr(blk, "header", None)
                out.append(
                    {
                        "height": getattr(hdr, "height", None),
                        "hash": blk.block_hash() if hasattr(blk, "block_hash") else "",
                        "prev_hash": getattr(hdr, "prev_hash", ""),
                        "timestamp": getattr(hdr, "timestamp", None),
                        "bits": getattr(hdr, "bits", None),
                        "tx_count": len(getattr(blk, "txs", [])),
                    }
                )
            return out

        file_blocks = self._load_blocks()
        out = []
        for blk in reversed(file_blocks[-max(1, limit):]):
            header = blk.get("header", {})
            out.append(
                {
                    "height": header.get("height"),
                    "hash": "",
                    "prev_hash": header.get("prev_hash"),
                    "timestamp": header.get("timestamp"),
                    "bits": header.get("bits"),
                    "tx_count": len(blk.get("txs", [])),
                }
            )
        return out

    def block_get(self, block_hash: str = "", height: Optional[int] = None) -> Optional[Dict[str, Any]]:
        blocks = getattr(self.db, "blocks", None)
        if isinstance(blocks, list):
            for blk in blocks:
                hdr = getattr(blk, "header", None)
                h = blk.block_hash() if hasattr(blk, "block_hash") else ""
                if block_hash and h == block_hash:
                    return blk.to_dict() if hasattr(blk, "to_dict") else {"hash": h}
                if height is not None and getattr(hdr, "height", None) == height:
                    return blk.to_dict() if hasattr(blk, "to_dict") else {"height": height}

        for blk in self._load_blocks():
            hdr = blk.get("header", {})
            if height is not None and hdr.get("height") == height:
                return blk
        return None


class RamiaCoreUIHandler(BaseHTTPRequestHandler):
    ctxp: aicore_plus.AppContextPlus
    datadir: str

    def _send(self, status: int, ctype: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        self._send(status, "application/json; charset=utf-8", _json_bytes(payload))

    def _serve_static(self, rel_path: str) -> bool:
        p = Path("coreui") / rel_path
        if not p.exists() or not p.is_file():
            return False
        ctype, _ = mimetypes.guess_type(str(p))
        self._send(200, ctype or "application/octet-stream", p.read_bytes())
        return True

    def _query_json(self) -> Dict[str, Any]:
        parsed = urlparse(self.path)
        data: Dict[str, Any] = {}
        for k, vals in parse_qs(parsed.query, keep_blank_values=True).items():
            data[k] = vals[-1] if vals else ""
        return data

    def _post_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            if self._serve_static("core_dashboard.html"):
                return
            self._send_json({"ok": False, "error": "missing_dashboard_html", "path": "coreui/core_dashboard.html"}, 404)
            return
        if path == "/core_dashboard.js":
            if self._serve_static("core_dashboard.js"):
                return
            self._send_json({"ok": False, "error": "missing_dashboard_js", "path": "coreui/core_dashboard.js"}, 404)
            return
        if path == "/core_dashboard.css":
            if self._serve_static("core_dashboard.css"):
                return
            self._send_json({"ok": False, "error": "missing_dashboard_css", "path": "coreui/core_dashboard.css"}, 404)
            return

        if path.startswith("/api/"):
            self._handle_api(path, self._query_json())
            return

        self._send(404, "text/plain; charset=utf-8", b"not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if not path.startswith("/api/"):
            self._send(404, "text/plain; charset=utf-8", b"not found")
            return
        try:
            data = self._post_json()
        except Exception:
            self._send_json({"ok": False, "error": "bad_json"}, 400)
            return
        self._handle_api(path, data)

    def _handle_api(self, path: str, data: Dict[str, Any]) -> None:
        try:
            # Forward routes to existing core implementation.
            if path in {"/api/status", "/api/wallet_create", "/api/wallet_info", "/api/send", "/api/mine"}:
                proxy = SimpleNamespace(ctxp=self.ctxp)
                out = aicore_plus.LocalHandlerPlus.route(proxy, path, data)
                self._send_json(out)
                return

            db = self.ctxp.core.db()
            adapter = ReadOnlyChainAdapter(self.datadir, db)

            if path == "/api/balance":
                addr = str(data.get("addr") or data.get("address") or "")
                if not addr and self.ctxp.wallet.exists():
                    addr = str(self.ctxp.wallet.load().get("address", ""))
                self._send_json({"ok": True, "address": addr, "balance": adapter.balance(addr)})
                return

            if path == "/api/tx_list":
                limit = int(data.get("limit", 50))
                self._send_json({"ok": True, "items": adapter.tx_list(limit=max(1, min(limit, 500)))})
                return

            if path == "/api/mempool_list":
                self._send_json({"ok": True, "items": adapter.mempool_list()})
                return

            if path == "/api/blocks_latest":
                limit = int(data.get("limit", 10))
                self._send_json({"ok": True, "items": adapter.blocks_latest(limit=max(1, min(limit, 200)))})
                return

            if path == "/api/block_get":
                block_hash = str(data.get("hash", ""))
                height_raw = data.get("height")
                height = int(height_raw) if height_raw not in (None, "") else None
                blk = adapter.block_get(block_hash=block_hash, height=height)
                if blk is None:
                    self._send_json({"ok": False, "error": "not_found"}, 404)
                    return
                self._send_json({"ok": True, "block": blk})
                return

            self._send_json({"ok": False, "error": "unknown_endpoint"}, 404)
        except Exception as exc:
            self._send_json({"ok": False, "error": "internal_error", "detail": str(exc)}, 500)


def run_server(ctxp: aicore_plus.AppContextPlus, datadir: str, host: str, port: int) -> None:
    class ThreadingHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True

    RamiaCoreUIHandler.ctxp = ctxp
    RamiaCoreUIHandler.datadir = datadir

    httpd = ThreadingHTTPServer((host, port), RamiaCoreUIHandler)
    print(f"[ramia-core-ui] web=http://{host}:{port}")
    httpd.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(prog="ramia_core_ui")
    parser.add_argument("--guardian-model", required=True)
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--datadir", default="./aichain_data")

    parser.add_argument("--wallet-file", default="./wallet.json")
    parser.add_argument("--threshold", type=float, default=0.7)
    parser.add_argument("--privacy-mode", default="receipt_only")
    parser.add_argument("--fleet-state", default="./fleet_state.json")
    parser.add_argument("--fleet-size", type=int, default=800)
    parser.add_argument("--fleet-seed", type=int, default=1337)
    parser.add_argument("--committee-size", type=int, default=9)
    parser.add_argument("--burst-state", default="./burst_state.json")
    parser.add_argument("--burst-window", type=int, default=60)
    parser.add_argument("--burst-max", type=int, default=10)
    parser.add_argument("--market-state", default="./market_secure_state.bin")
    parser.add_argument("--secret-file", default="./market_secret.key")
    parser.add_argument("--audit-log", default="./audit_log.jsonl")
    args = parser.parse_args()

    core_args = argparse.Namespace(
        datadir=args.datadir,
        guardian_model=args.guardian_model,
        threshold=args.threshold,
        privacy_mode=args.privacy_mode,
        fleet_state=args.fleet_state,
        fleet_size=args.fleet_size,
        fleet_seed=args.fleet_seed,
        committee_size=args.committee_size,
        burst_state=args.burst_state,
        burst_window=args.burst_window,
        burst_max=args.burst_max,
        market_state=args.market_state,
        secret_file=args.secret_file,
        audit_log=args.audit_log,
    )
    ctxp = aicore_plus.AppContextPlus(core_args, wallet_file=args.wallet_file)
    run_server(ctxp, datadir=args.datadir, host=args.host, port=args.port)
 main


if __name__ == "__main__":
    main()
