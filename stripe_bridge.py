#!/usr/bin/env python3
"""Stripe grant-token bridge for local RamIA credit redemption."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, Tuple


class StripeGrantBridge:
    def __init__(self, secret: str | None = None):
        env_secret = secret or os.environ.get("STRIPE_GRANT_SECRET") or os.environ.get("STRIPE_WEBHOOK_SECRET")
        if not env_secret:
            raise RuntimeError("Missing STRIPE_GRANT_SECRET (or STRIPE_WEBHOOK_SECRET) for local token verification")
        self.secret = env_secret.encode("utf-8")

    @staticmethod
    def _b64d(part: str) -> bytes:
        pad = "=" * ((4 - len(part) % 4) % 4)
        return base64.urlsafe_b64decode((part + pad).encode("utf-8"))

    def _verify_signature(self, header_b64: str, payload_b64: str, signature_b64: str) -> bool:
        data = f"{header_b64}.{payload_b64}".encode("utf-8")
        expected = hmac.new(self.secret, data, hashlib.sha256).digest()
        actual = self._b64d(signature_b64)
        return hmac.compare_digest(expected, actual)

    def parse_and_validate(self, token: str) -> Dict[str, Any]:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("invalid_token_format")

        h_b64, p_b64, s_b64 = parts
        if not self._verify_signature(h_b64, p_b64, s_b64):
            raise ValueError("invalid_token_signature")

        header = json.loads(self._b64d(h_b64).decode("utf-8"))
        payload = json.loads(self._b64d(p_b64).decode("utf-8"))

        if header.get("alg") != "HS256":
            raise ValueError("unsupported_algorithm")

        now = int(time.time())
        exp = int(payload.get("expires_at", 0))
        if exp <= now:
            raise ValueError("expired_token")

        payload["credits"] = int(payload.get("credits", 0))
        if payload["credits"] <= 0:
            raise ValueError("invalid_credits")
        payload["renter"] = str(payload.get("renter", "")).strip()
        if not payload["renter"]:
            raise ValueError("invalid_renter")

        return payload


class MarketCreditsAdapter:
    """Adapter layer to update credits without touching existing core modules."""

    def __init__(self, app_context_plus: Any):
        self.ctxp = app_context_plus
        self.core = app_context_plus.core

    def grant(self, renter: str, credits: int, reason: str, ref: str) -> Dict[str, Any]:
        if renter not in self.core.market.state["renters"]:
            self.core.market.renter_create(renter)
        self.core.market.add_credits(renter, int(credits))
        self.core.audit.append({
            "type": "stripe_grant_redeem",
            "renter": renter,
            "credits": int(credits),
            "reason": reason,
            "reference": ref,
        })
        self.core.save()
        return {
            "ok": True,
            "renter": renter,
            "credited": int(credits),
            "credits_total": int(self.core.market.state["credits"].get(renter, 0)),
        }


def redeem_grant_token(app_context_plus: Any, token: str) -> Tuple[bool, Dict[str, Any]]:
    try:
        bridge = StripeGrantBridge()
        payload = bridge.parse_and_validate(token)
        out = MarketCreditsAdapter(app_context_plus).grant(
            renter=payload["renter"],
            credits=payload["credits"],
            reason="stripe_checkout",
            ref=payload.get("session_id", payload.get("jti", "unknown")),
        )
        return True, out
    except Exception as exc:
        return False, {"ok": False, "error": str(exc)}
