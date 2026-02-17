#!/usr/bin/env python3
"""Stripe webhook listener that provisions secure wallets and bot assignments.

Environment variables:
- STRIPE_SECRET_KEY: Stripe API key (used to initialize SDK).
- STRIPE_WEBHOOK_SECRET: Webhook signing secret (whsec_...).
- WALLET_ENCRYPTION_PASSPHRASE: Server-only passphrase used to derive encryption keys.
- WEBHOOK_DB_PATH (optional): SQLite path for wallet + assignment storage.
- LOG_LEVEL (optional): Python logging level (default INFO).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import sqlite3
import time
from typing import Any

import stripe
from flask import Flask, Request, jsonify, request

from wallet_secure import _aead_encrypt, _address_from_pub, _b64e, _derive_key, _new_signing_material


LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO), format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("stripe_webhook")

app = Flask(__name__)

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
WALLET_ENCRYPTION_PASSPHRASE = os.environ.get("WALLET_ENCRYPTION_PASSPHRASE", "")
DB_PATH = os.environ.get("WEBHOOK_DB_PATH", "./data/stripe_webhook.sqlite3")

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY


class ConfigError(RuntimeError):
    """Raised when required environment variables are missing."""


def _require_config() -> None:
    missing: list[str] = []
    if not STRIPE_SECRET_KEY:
        missing.append("STRIPE_SECRET_KEY")
    if not STRIPE_WEBHOOK_SECRET:
        missing.append("STRIPE_WEBHOOK_SECRET")
    if len(WALLET_ENCRYPTION_PASSPHRASE) < 16:
        missing.append("WALLET_ENCRYPTION_PASSPHRASE(len>=16)")
    if missing:
        raise ConfigError(f"missing_or_invalid_env:{','.join(missing)}")


def _db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS user_wallets (
                user_id TEXT PRIMARY KEY,
                address TEXT NOT NULL UNIQUE,
                public_key TEXT NOT NULL,
                curve TEXT NOT NULL,
                encrypted_private_key_json TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_bot_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                wallet_address TEXT NOT NULL,
                credits INTEGER NOT NULL,
                stripe_session_id TEXT NOT NULL,
                stripe_event_id TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS processed_events (
                stripe_event_id TEXT PRIMARY KEY,
                stripe_session_id TEXT,
                user_id TEXT,
                status TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            """
        )


init_db()

def _encrypt_private_key(private_key: bytes, public_identity: dict[str, Any]) -> dict[str, Any]:
    salt = secrets.token_bytes(16)
    kdf = _derive_key(WALLET_ENCRYPTION_PASSPHRASE, salt)
    nonce = secrets.token_bytes(12)
    aad = json.dumps({"v": 1, "public": public_identity}, sort_keys=True).encode("utf-8")
    encrypted = _aead_encrypt(kdf.key, nonce, private_key, aad)
    return {
        "metadata": {"version": 1, "format": "ramia.wallet.secure"},
        "kdf": kdf.config,
        "aead": encrypted,
        "public": public_identity,
    }


def _create_wallet_record(conn: sqlite3.Connection, user_id: str) -> tuple[str, str]:
    """Create wallet once per user. Returns (address, public_key)."""
    existing = conn.execute(
        "SELECT address, public_key FROM user_wallets WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if existing:
        return str(existing["address"]), str(existing["public_key"])

    signing = _new_signing_material()
    public_identity = {
        "address": _address_from_pub(signing["public"]),
        "public_key": _b64e(signing["public"]),
        "curve": signing["type"],
        "label": f"user:{user_id}",
    }
    encrypted_wallet = _encrypt_private_key(signing["private"], public_identity)

    conn.execute(
        """
        INSERT INTO user_wallets (user_id, address, public_key, curve, encrypted_private_key_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            public_identity["address"],
            public_identity["public_key"],
            public_identity["curve"],
            json.dumps(encrypted_wallet, separators=(",", ":")),
            int(time.time()),
        ),
    )
    return str(public_identity["address"]), str(public_identity["public_key"])


def _idempotency_key(event_id: str, session_id: str) -> str:
    return hashlib.sha256(f"{event_id}:{session_id}".encode("utf-8")).hexdigest()


def _handle_checkout_completed(event: dict[str, Any]) -> dict[str, Any]:
    session = event["data"]["object"]
    metadata = session.get("metadata") or {}

    user_id = str(metadata.get("user_id") or metadata.get("renter") or "").strip()
    if not user_id:
        raise ValueError("missing_user_id_in_metadata")

    bots_purchased = int(metadata.get("bots_purchased") or metadata.get("bots_count") or 1)
    if bots_purchased <= 0:
        raise ValueError("invalid_bots_purchased")

    session_id = str(session.get("id") or "")
    event_id = str(event.get("id") or "")
    if not session_id or not event_id:
        raise ValueError("missing_event_or_session_id")

    with _db() as conn:
        already = conn.execute("SELECT 1 FROM processed_events WHERE stripe_event_id = ?", (event_id,)).fetchone()
        if already:
            logger.info("webhook.idempotent event=%s user=%s", event_id, user_id)
            wallet = conn.execute("SELECT address FROM user_wallets WHERE user_id = ?", (user_id,)).fetchone()
            return {
                "ok": True,
                "status": "already_processed",
                "user_id": user_id,
                "wallet_address": str(wallet["address"]) if wallet else None,
            }

        wallet_address, _public_key = _create_wallet_record(conn, user_id)
        conn.execute(
            """
            INSERT INTO user_bot_assignments (user_id, wallet_address, credits, stripe_session_id, stripe_event_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, wallet_address, bots_purchased, session_id, event_id, int(time.time())),
        )
        conn.execute(
            """
            INSERT INTO processed_events (stripe_event_id, stripe_session_id, user_id, status, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (event_id, session_id, user_id, _idempotency_key(event_id, session_id), int(time.time())),
        )
        conn.commit()

    logger.info(
        "webhook.assigned event=%s session=%s user=%s bots=%s wallet=%s",
        event_id,
        session_id,
        user_id,
        bots_purchased,
        wallet_address,
    )
    return {"ok": True, "status": "assigned", "user_id": user_id, "wallet_address": wallet_address, "bots_assigned": bots_purchased}


def _construct_stripe_event(req: Request) -> dict[str, Any]:
    signature = req.headers.get("Stripe-Signature", "")
    payload = req.get_data(as_text=True)
    if not signature:
        raise ValueError("missing_stripe_signature")

    event = stripe.Webhook.construct_event(payload=payload, sig_header=signature, secret=STRIPE_WEBHOOK_SECRET)
    return dict(event)


@app.route("/webhook", methods=["POST"])
def webhook() -> Any:
    try:
        _require_config()
        event = _construct_stripe_event(request)

        event_type = str(event.get("type") or "")
        if event_type != "checkout.session.completed":
            logger.info("webhook.ignored type=%s", event_type)
            return jsonify({"received": True, "ignored": event_type}), 200

        result = _handle_checkout_completed(event)
        return jsonify(result), 200
    except ConfigError as exc:
        logger.error("webhook.config_error=%s", exc)
        return jsonify({"error": str(exc)}), 500
    except ValueError as exc:
        logger.warning("webhook.bad_request=%s", exc)
        return jsonify({"error": str(exc)}), 400
    except stripe.error.SignatureVerificationError:
        logger.warning("webhook.invalid_signature")
        return jsonify({"error": "invalid_signature"}), 400
    except Exception as exc:  # noqa: BLE001
        logger.exception("webhook.internal_error")
        return jsonify({"error": f"internal_error:{type(exc).__name__}"}), 500


@app.get("/healthz")
def healthz() -> Any:
    return jsonify({"ok": True}), 200


if __name__ == "__main__":
    init_db()
    _require_config()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
