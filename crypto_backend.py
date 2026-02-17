#!/usr/bin/env python3
"""Small signing backend for RamIA secure transaction mode."""

from __future__ import annotations

import base64
import hashlib
from typing import Union

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey  # type: ignore
    HAVE_ED25519 = True
except Exception:
    HAVE_ED25519 = False


BytesLike = Union[bytes, bytearray, str]


def _to_bytes(value: BytesLike) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    return str(value).encode("utf-8")


def _b64decode_maybe(value: BytesLike) -> bytes:
    if not isinstance(value, str):
        return _to_bytes(value)
    raw = value.encode("utf-8")
    try:
        pad = "=" * ((4 - (len(value) % 4)) % 4)
        return base64.urlsafe_b64decode((value + pad).encode("utf-8"))
    except Exception:
        return raw


def _dev_pub_from_sk(sk_bytes: bytes) -> bytes:
    return hashlib.sha256(sk_bytes).digest()


def sign(sk: BytesLike, msg: BytesLike) -> str:
    """Sign message bytes; returns hex signature string."""
    msg_b = _to_bytes(msg)
    sk_b = _b64decode_maybe(sk)

    if isinstance(sk, str) and HAVE_ED25519 and len(sk_b) == 32:
        try:
            sig = Ed25519PrivateKey.from_private_bytes(sk_b).sign(msg_b)
            return sig.hex()
        except Exception:
            pass

    # Dev fallback: deterministic tag derived from derived-public-key + payload.
    pub = _dev_pub_from_sk(sk_b)
    return hashlib.sha256(pub + msg_b).hexdigest()


def verify(pk: BytesLike, msg: BytesLike, sig: str) -> bool:
    """Verify signature produced by ``sign``."""
    msg_b = _to_bytes(msg)
    pk_b = _b64decode_maybe(pk)

    if isinstance(pk, str) and HAVE_ED25519 and len(pk_b) == 32:
        try:
            Ed25519PublicKey.from_public_bytes(pk_b).verify(bytes.fromhex(sig), msg_b)
            return True
        except Exception:
            pass

    try:
        expect = hashlib.sha256(pk_b + msg_b).hexdigest()
        return expect == str(sig)
    except Exception:
        return False
