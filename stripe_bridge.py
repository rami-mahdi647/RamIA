#!/usr/bin/env python3
"""Stripe grant bridge for local RamIA redemption."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
import json
from typing import Any, Dict


def _b64d(part: str) -> bytes:
    pad = "=" * ((4 - len(part) % 4) % 4)
    return base64.urlsafe_b64decode((part + pad).encode("utf-8"))


def verify_grant_token(token: str) -> Dict[str, Any]:
    secret = os.environ.get("STRIPE_GRANT_SECRET")
    if not secret:
        raise RuntimeError("missing_STRIPE_GRANT_SECRET")

    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("invalid_token_format")
    h_b64, p_b64, s_b64 = parts

    data = f"{h_b64}.{p_b64}".encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), data, hashlib.sha256).digest()
    actual = _b64d(s_b64)
    if not hmac.compare_digest(expected, actual):
        raise ValueError("invalid_token_signature")

    header = json.loads(_b64d(h_b64).decode("utf-8"))
    payload = json.loads(_b64d(p_b64).decode("utf-8"))

    if header.get("alg") != "HS256":
        raise ValueError("unsupported_algorithm")

    now = int(time.time())
    expires_ts = int(payload.get("expires_ts", 0))
    if expires_ts <= now:
        raise ValueError("expired_token")

    payload["bots_count"] = int(payload.get("bots_count", 0))
    payload["credits_to_add"] = int(payload.get("credits_to_add", 0))
    payload["renter"] = str(payload.get("renter", "")).strip()

    if payload["bots_count"] <= 0:
        raise ValueError("invalid_bots_count")
    if payload["credits_to_add"] <= 0:
        raise ValueError("invalid_credits")
    if not payload["renter"]:
        raise ValueError("invalid_renter")

    return payload


def apply_credit_to_market(core_market: Any, renter: str, credits_to_add: int) -> Dict[str, Any]:
    if renter not in core_market.state["renters"]:
        core_market.renter_create(renter)
    core_market.add_credits(renter, int(credits_to_add))
    return {
        "ok": True,
        "renter": renter,
        "credited": int(credits_to_add),
        "credits_total": int(core_market.state["credits"].get(renter, 0)),
    }


def redeem_grant_token(ctxp: Any, token: str, expected_renter: str | None = None) -> tuple[bool, Dict[str, Any]]:
    token = str(token or "").strip()
    if not token:
        return False, {"ok": False, "error": "missing_grant_token"}

    try:
        payload = verify_grant_token(token)
    except Exception as exc:
        return False, {"ok": False, "error": str(exc)}

    renter = payload["renter"]
    if expected_renter is not None and renter != expected_renter:
        return False, {"ok": False, "error": "renter_mismatch"}

    grant_id = str(payload.get("jti") or payload.get("session_id") or "").strip()
    if not grant_id:
        return False, {"ok": False, "error": "missing_grant_id"}

    redeemed = ctxp.core.market.state.setdefault("redeemed_grants", {})
    if grant_id in redeemed:
        return False, {"ok": False, "error": "grant_already_redeemed", "grant_id": grant_id}

    out = apply_credit_to_market(ctxp.core.market, renter, payload["credits_to_add"])
    redeemed[grant_id] = int(time.time())

    ctxp.core.audit.append(
        {
            "type": "stripe_grant_redeem_v1",
            "renter": renter,
            "credits": payload["credits_to_add"],
            "bots_count": payload["bots_count"],
            "session_id": payload.get("session_id", "unknown"),
            "jti": payload.get("jti"),
            "grant_id": grant_id,
        }
    )
    ctxp.core.save()
    out["grant_id"] = grant_id
    return True, out
