"""Transaction private payload encryption helpers.

Exposes:
- encrypt_private_payload(recipient_pubkey, payload_json, tx_header) -> blob
- decrypt_private_payload(recipient_secretkey, blob, tx_header) -> payload_json

Design:
- Payload is encrypted with AEAD (ChaCha20-Poly1305 preferred, AES-GCM fallback).
- AEAD AAD is the canonical transaction header tuple: txid/from/to/timestamp.
- CEK wrapping prefers libsodium sealed boxes (PyNaCl).
- If sealed boxes are unavailable, falls back to X25519 ECDH + HKDF + AEAD key wrap.
- Public structures only need the returned encrypted blob.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any, Dict

# Optional libsodium sealed boxes
try:
    from nacl.public import PublicKey, PrivateKey, SealedBox  # type: ignore

    HAS_SEALEDBOX = True
except Exception:  # pragma: no cover - optional dependency
    HAS_SEALEDBOX = False

# Optional cryptography primitives (AEAD + ECDH fallback)
try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import x25519
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    HAS_CRYPTOGRAPHY = True
except Exception:  # pragma: no cover - optional dependency
    HAS_CRYPTOGRAPHY = False


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii")


def _b64d(data: str) -> bytes:
    return base64.urlsafe_b64decode(data.encode("ascii"))


def _canonical_header(tx_header: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(tx_header, dict):
        raise TypeError("tx_header must be a dict")

    aliases = {
        "txid": ["txid", "id", "hash"],
        "from": ["from", "sender", "from_addr", "from_address"],
        "to": ["to", "recipient", "to_addr", "to_address"],
        "timestamp": ["timestamp", "ts", "time", "created_at"],
    }

    out: Dict[str, Any] = {}
    for canonical, names in aliases.items():
        for name in names:
            if name in tx_header:
                out[canonical] = tx_header[name]
                break
        if canonical not in out:
            raise ValueError(f"Missing canonical header field: {canonical}")

    return out


def _aad_bytes(tx_header: Dict[str, Any]) -> bytes:
    canonical = _canonical_header(tx_header)
    return json.dumps(canonical, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _payload_to_bytes(payload_json: Any) -> bytes:
    if isinstance(payload_json, (bytes, bytearray)):
        return bytes(payload_json)
    if isinstance(payload_json, str):
        try:
            parsed = json.loads(payload_json)
            return json.dumps(parsed, separators=(",", ":"), sort_keys=True).encode("utf-8")
        except json.JSONDecodeError:
            return payload_json.encode("utf-8")
    return json.dumps(payload_json, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _bytes_to_payload(payload_bytes: bytes) -> Any:
    try:
        return json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        return payload_bytes.decode("utf-8", errors="replace")


def _select_content_aead():
    if HAS_CRYPTOGRAPHY and "ChaCha20Poly1305" in globals():
        return "chacha20poly1305"
    if HAS_CRYPTOGRAPHY and "AESGCM" in globals():
        return "aesgcm"
    raise RuntimeError("No AEAD backend available. Install 'cryptography'.")


def _aead_encrypt(alg: str, key: bytes, nonce: bytes, plaintext: bytes, aad: bytes) -> bytes:
    if alg == "chacha20poly1305":
        return ChaCha20Poly1305(key).encrypt(nonce, plaintext, aad)
    if alg == "aesgcm":
        return AESGCM(key).encrypt(nonce, plaintext, aad)
    raise ValueError(f"Unsupported AEAD algorithm: {alg}")


def _aead_decrypt(alg: str, key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes:
    if alg == "chacha20poly1305":
        return ChaCha20Poly1305(key).decrypt(nonce, ciphertext, aad)
    if alg == "aesgcm":
        return AESGCM(key).decrypt(nonce, ciphertext, aad)
    raise ValueError(f"Unsupported AEAD algorithm: {alg}")


def _normalize_pubkey(recipient_pubkey: Any) -> bytes:
    if isinstance(recipient_pubkey, (bytes, bytearray)):
        key = bytes(recipient_pubkey)
    elif isinstance(recipient_pubkey, str):
        key = _b64d(recipient_pubkey) if not all(c in "0123456789abcdefABCDEF" for c in recipient_pubkey) else bytes.fromhex(recipient_pubkey)
    else:
        raise TypeError("recipient_pubkey must be bytes or str")
    if len(key) != 32:
        raise ValueError("recipient_pubkey must be 32 bytes (Curve25519/X25519 public key)")
    return key


def _normalize_secretkey(recipient_secretkey: Any) -> bytes:
    if isinstance(recipient_secretkey, (bytes, bytearray)):
        key = bytes(recipient_secretkey)
    elif isinstance(recipient_secretkey, str):
        key = _b64d(recipient_secretkey) if not all(c in "0123456789abcdefABCDEF" for c in recipient_secretkey) else bytes.fromhex(recipient_secretkey)
    else:
        raise TypeError("recipient_secretkey must be bytes or str")
    if len(key) != 32:
        raise ValueError("recipient_secretkey must be 32 bytes (Curve25519/X25519 private key)")
    return key


def _wrap_key_sealedbox(recipient_pubkey: bytes, cek: bytes) -> Dict[str, str]:
    sealed = SealedBox(PublicKey(recipient_pubkey)).encrypt(cek)
    return {"wrap": "sealedbox", "wrapped_cek": _b64e(sealed)}


def _unwrap_key_sealedbox(recipient_secretkey: bytes, wrapped: Dict[str, str]) -> bytes:
    sealed = _b64d(wrapped["wrapped_cek"])
    return SealedBox(PrivateKey(recipient_secretkey)).decrypt(sealed)


def _wrap_key_ecdh(recipient_pubkey: bytes, cek: bytes, aad: bytes) -> Dict[str, str]:
    if not HAS_CRYPTOGRAPHY:
        raise RuntimeError("ECDH fallback needs 'cryptography' package")

    eph_priv = x25519.X25519PrivateKey.generate()
    eph_pub = eph_priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)

    recipient = x25519.X25519PublicKey.from_public_bytes(recipient_pubkey)
    shared = eph_priv.exchange(recipient)
    kek = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"tx_privacy/ecdh-wrap").derive(shared)

    wrap_alg = "chacha20poly1305" if "ChaCha20Poly1305" in globals() else "aesgcm"
    nonce = os.urandom(12)
    wrapped_cek = _aead_encrypt(wrap_alg, kek, nonce, cek, aad)

    return {
        "wrap": "ecdh-aead",
        "wrap_alg": wrap_alg,
        "ephemeral_pubkey": _b64e(eph_pub),
        "wrap_nonce": _b64e(nonce),
        "wrapped_cek": _b64e(wrapped_cek),
    }


def _unwrap_key_ecdh(recipient_secretkey: bytes, wrapped: Dict[str, str], aad: bytes) -> bytes:
    if not HAS_CRYPTOGRAPHY:
        raise RuntimeError("ECDH fallback needs 'cryptography' package")

    recipient_priv = x25519.X25519PrivateKey.from_private_bytes(recipient_secretkey)
    eph_pub = x25519.X25519PublicKey.from_public_bytes(_b64d(wrapped["ephemeral_pubkey"]))
    shared = recipient_priv.exchange(eph_pub)
    kek = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"tx_privacy/ecdh-wrap").derive(shared)

    return _aead_decrypt(
        wrapped["wrap_alg"],
        kek,
        _b64d(wrapped["wrap_nonce"]),
        _b64d(wrapped["wrapped_cek"]),
        aad,
    )


def encrypt_private_payload(recipient_pubkey: Any, payload_json: Any, tx_header: Dict[str, Any]) -> str:
    """Encrypt private payload for a recipient and return an opaque blob string."""
    pub = _normalize_pubkey(recipient_pubkey)
    aad = _aad_bytes(tx_header)

    payload = _payload_to_bytes(payload_json)
    content_alg = _select_content_aead()
    cek = os.urandom(32)
    nonce = os.urandom(12)
    ciphertext = _aead_encrypt(content_alg, cek, nonce, payload, aad)

    if HAS_SEALEDBOX:
        wrapped = _wrap_key_sealedbox(pub, cek)
    else:
        wrapped = _wrap_key_ecdh(pub, cek, aad)

    envelope = {
        "v": 1,
        "content_alg": content_alg,
        "content_nonce": _b64e(nonce),
        "ciphertext": _b64e(ciphertext),
        **wrapped,
    }
    return _b64e(json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def decrypt_private_payload(recipient_secretkey: Any, blob: str, tx_header: Dict[str, Any]) -> Any:
    """Decrypt an encrypted blob and return the original JSON payload."""
    sk = _normalize_secretkey(recipient_secretkey)
    aad = _aad_bytes(tx_header)

    envelope = json.loads(_b64d(blob).decode("utf-8"))
    wrap_method = envelope.get("wrap")

    if wrap_method == "sealedbox":
        cek = _unwrap_key_sealedbox(sk, envelope)
    elif wrap_method == "ecdh-aead":
        cek = _unwrap_key_ecdh(sk, envelope, aad)
    else:
        raise ValueError(f"Unsupported key-wrap method: {wrap_method}")

    plaintext = _aead_decrypt(
        envelope["content_alg"],
        cek,
        _b64d(envelope["content_nonce"]),
        _b64d(envelope["ciphertext"]),
        aad,
    )
    return _bytes_to_payload(plaintext)
