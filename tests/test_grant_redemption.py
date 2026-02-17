import base64
import hashlib
import hmac
import json
import os
import types

import stripe_bridge


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _build_token(secret: str, payload: dict) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    h = _b64e(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(secret.encode("utf-8"), f"{h}.{p}".encode("utf-8"), hashlib.sha256).digest()
    s = _b64e(sig)
    return f"{h}.{p}.{s}"


class DummyMarket:
    def __init__(self):
        self.state = {"renters": {}, "credits": {}}

    def renter_create(self, renter: str):
        self.state["renters"][renter] = {"ok": True}
        self.state["credits"].setdefault(renter, 0)

    def add_credits(self, renter: str, credits: int):
        self.state["credits"][renter] = int(self.state["credits"].get(renter, 0)) + int(credits)


class DummyAudit:
    def __init__(self):
        self.items = []

    def append(self, item):
        self.items.append(item)


class DummyCore:
    def __init__(self, datadir: str):
        self.market = DummyMarket()
        self.audit = DummyAudit()
        self.args = types.SimpleNamespace(datadir=datadir)
        self.saved = 0

    def save(self):
        self.saved += 1


class DummyCtx:
    def __init__(self, datadir: str):
        self.core = DummyCore(datadir)


def test_first_redeem_is_successful(tmp_path, monkeypatch):
    monkeypatch.setenv("STRIPE_GRANT_SECRET", "secret123")
    ctx = DummyCtx(str(tmp_path))
    payload = {
        "renter": "alice",
        "bots_count": 10,
        "credits_to_add": 500,
        "expires_ts": 4_102_444_800,
        "session_id": "sess-1",
        "jti": "grant-1",
    }
    token = _build_token("secret123", payload)

    ok, out = stripe_bridge.redeem_grant_token(ctx, token)

    assert ok is True
    assert out["ok"] is True
    assert out["credited"] == 500
    assert out["grant_id"] == "grant-1"
    assert ctx.core.market.state["credits"]["alice"] == 500


def test_second_redeem_with_same_jti_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("STRIPE_GRANT_SECRET", "secret123")
    ctx = DummyCtx(str(tmp_path))
    payload = {
        "renter": "alice",
        "bots_count": 10,
        "credits_to_add": 500,
        "expires_ts": 4_102_444_800,
        "session_id": "sess-1",
        "jti": "grant-dup",
    }
    token = _build_token("secret123", payload)

    ok1, _ = stripe_bridge.redeem_grant_token(ctx, token)
    ok2, out2 = stripe_bridge.redeem_grant_token(ctx, token)

    assert ok1 is True
    assert ok2 is False
    assert out2["ok"] is False
    assert out2["error"] == "grant_already_redeemed"
    assert ctx.core.market.state["credits"]["alice"] == 500


def test_expired_token_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("STRIPE_GRANT_SECRET", "secret123")
    ctx = DummyCtx(str(tmp_path))
    payload = {
        "renter": "alice",
        "bots_count": 10,
        "credits_to_add": 500,
        "expires_ts": 1,
        "session_id": "sess-expired",
        "jti": "grant-expired",
    }
    token = _build_token("secret123", payload)

    ok, out = stripe_bridge.redeem_grant_token(ctx, token)

    assert ok is False
    assert out["ok"] is False
    assert out["error"] == "expired_token"
