 codex/create-crypto_backend.py-with-provider-selection
"""Unified crypto backend with strict provider selection and nonce handling.

Provider priority:
1) libsodium bindings (PyNaCl) - preferred
2) cryptography primitives
3) insecure dev fallback only when explicitly enabled
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Optional, Tuple


class INSECURE_CRYPTO_UNAVAILABLE(RuntimeError):
    """Raised when no approved crypto backend is available."""


_DEV_MODE_ENV = "CRYPTO_BACKEND_ALLOW_INSECURE_DEV_MODE"


class _BaseProvider:
    name: str = "base"
    nonce_size: int = 0
    has_sealed_boxes: bool = False

    def random_bytes(self, length: int) -> bytes:
        if length <= 0:
            raise ValueError("length must be > 0")
        return os.urandom(length)

    def kdf(self, password: bytes | str, salt: bytes, length: int = 32) -> bytes:
        raise NotImplementedError

    def aead_encrypt(
        self,
        key: bytes,
        plaintext: bytes,
        associated_data: Optional[bytes] = None,
        nonce: Optional[bytes] = None,
    ) -> Tuple[bytes, bytes]:
        raise NotImplementedError

    def aead_decrypt(
        self,
        key: bytes,
        ciphertext: bytes,
        nonce: bytes,
        associated_data: Optional[bytes] = None,
    ) -> bytes:
        raise NotImplementedError

    def sign(self, private_key: bytes, message: bytes) -> bytes:
        raise NotImplementedError

    def verify(self, public_key: bytes, message: bytes, signature: bytes) -> bool:
        raise NotImplementedError

    def seal_to_public_key(self, public_key: bytes, plaintext: bytes) -> bytes:
        raise NotImplementedError("sealed boxes unsupported by current provider")

    def open_sealed_box(self, public_key: bytes, private_key: bytes, sealed: bytes) -> bytes:
        raise NotImplementedError("sealed boxes unsupported by current provider")

    def _resolve_nonce(self, nonce: Optional[bytes]) -> bytes:
        if nonce is None:
            return self.random_bytes(self.nonce_size)
        if len(nonce) != self.nonce_size:
            raise ValueError(f"Invalid nonce size: expected {self.nonce_size}, got {len(nonce)}")
        return nonce


class _SodiumProvider(_BaseProvider):
    name = "libsodium"
    nonce_size = 24  # XChaCha20-Poly1305-IETF
    has_sealed_boxes = True

    def __init__(self) -> None:
        from nacl import bindings, public, signing
        from nacl.exceptions import BadSignatureError, CryptoError

        self.bindings = bindings
        self.public = public
        self.signing = signing
        self.BadSignatureError = BadSignatureError
        self.CryptoError = CryptoError

        if not hasattr(bindings, "crypto_aead_xchacha20poly1305_ietf_encrypt"):
            raise ImportError("XChaCha20-Poly1305 not available in libsodium bindings")

    def kdf(self, password: bytes | str, salt: bytes, length: int = 32) -> bytes:
        if isinstance(password, str):
            password = password.encode("utf-8")
        if len(salt) < 16:
            raise ValueError("salt must be at least 16 bytes")
        return self.bindings.crypto_pwhash(
            length,
            password,
            salt[:16],
            self.bindings.crypto_pwhash_OPSLIMIT_MODERATE,
            self.bindings.crypto_pwhash_MEMLIMIT_MODERATE,
            self.bindings.crypto_pwhash_ALG_ARGON2ID13,
        )

    def aead_encrypt(
        self,
        key: bytes,
        plaintext: bytes,
        associated_data: Optional[bytes] = None,
        nonce: Optional[bytes] = None,
    ) -> Tuple[bytes, bytes]:
        if len(key) != self.bindings.crypto_aead_xchacha20poly1305_ietf_KEYBYTES:
            raise ValueError("key must be 32 bytes for XChaCha20-Poly1305")
        nonce = self._resolve_nonce(nonce)
        ad = associated_data if associated_data is not None else b""
        ct = self.bindings.crypto_aead_xchacha20poly1305_ietf_encrypt(
            plaintext, ad, nonce, key
        )
        return nonce, ct

    def aead_decrypt(
        self,
        key: bytes,
        ciphertext: bytes,
        nonce: bytes,
        associated_data: Optional[bytes] = None,
    ) -> bytes:
        if len(key) != self.bindings.crypto_aead_xchacha20poly1305_ietf_KEYBYTES:
            raise ValueError("key must be 32 bytes for XChaCha20-Poly1305")
        self._resolve_nonce(nonce)
        ad = associated_data if associated_data is not None else b""
        return self.bindings.crypto_aead_xchacha20poly1305_ietf_decrypt(
            ciphertext, ad, nonce, key
        )

    def sign(self, private_key: bytes, message: bytes) -> bytes:
        sk = self.signing.SigningKey(private_key)
        return sk.sign(message).signature

    def verify(self, public_key: bytes, message: bytes, signature: bytes) -> bool:
        vk = self.signing.VerifyKey(public_key)
        try:
            vk.verify(message, signature)
            return True
        except self.BadSignatureError:
            return False

    def seal_to_public_key(self, public_key: bytes, plaintext: bytes) -> bytes:
        pk = self.public.PublicKey(public_key)
        return self.public.SealedBox(pk).encrypt(plaintext)

    def open_sealed_box(self, public_key: bytes, private_key: bytes, sealed: bytes) -> bytes:
        pk = self.public.PublicKey(public_key)
        sk = self.public.PrivateKey(private_key)
        return self.public.SealedBox(sk).decrypt(sealed)


class _CryptographyProvider(_BaseProvider):
    name = "cryptography"

    def __init__(self) -> None:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
            Ed25519PublicKey,
        )
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

        self.InvalidSignature = InvalidSignature
        self.hashes = hashes
        self.Ed25519PrivateKey = Ed25519PrivateKey
        self.Ed25519PublicKey = Ed25519PublicKey
        self.AESGCM = AESGCM
        self.ChaCha20Poly1305 = ChaCha20Poly1305
        self.Scrypt = Scrypt

        # Prefer ChaCha20-Poly1305 when present.
        self._aead_ctor = ChaCha20Poly1305
        self._key_size = 32
        self.nonce_size = 12

    def kdf(self, password: bytes | str, salt: bytes, length: int = 32) -> bytes:
        if isinstance(password, str):
            password = password.encode("utf-8")
        if len(salt) < 16:
            raise ValueError("salt must be at least 16 bytes")
        return self.Scrypt(salt=salt, length=length, n=2**14, r=8, p=1).derive(password)

    def aead_encrypt(
        self,
        key: bytes,
        plaintext: bytes,
        associated_data: Optional[bytes] = None,
        nonce: Optional[bytes] = None,
    ) -> Tuple[bytes, bytes]:
        if len(key) != self._key_size:
            raise ValueError("key must be 32 bytes for ChaCha20-Poly1305")
        nonce = self._resolve_nonce(nonce)
        ct = self._aead_ctor(key).encrypt(nonce, plaintext, associated_data)
        return nonce, ct

    def aead_decrypt(
        self,
        key: bytes,
        ciphertext: bytes,
        nonce: bytes,
        associated_data: Optional[bytes] = None,
    ) -> bytes:
        if len(key) != self._key_size:
            raise ValueError("key must be 32 bytes for ChaCha20-Poly1305")
        self._resolve_nonce(nonce)
        return self._aead_ctor(key).decrypt(nonce, ciphertext, associated_data)

    def sign(self, private_key: bytes, message: bytes) -> bytes:
        sk = self.Ed25519PrivateKey.from_private_bytes(private_key)
        return sk.sign(message)

    def verify(self, public_key: bytes, message: bytes, signature: bytes) -> bool:
        pk = self.Ed25519PublicKey.from_public_bytes(public_key)
        try:
            pk.verify(signature, message)
            return True
        except self.InvalidSignature:
            return False


class _InsecureDevProvider(_BaseProvider):
    """Development-only fallback. Never use in production."""

    name = "insecure-dev"
    nonce_size = 24

    def kdf(self, password: bytes | str, salt: bytes, length: int = 32) -> bytes:
        if isinstance(password, str):
            password = password.encode("utf-8")
        return hashlib.pbkdf2_hmac("sha256", password, salt, 10_000, dklen=length)

    def _stream(self, key: bytes, nonce: bytes, length: int) -> bytes:
        out = bytearray()
        counter = 0
        while len(out) < length:
            out.extend(hashlib.blake2b(key + nonce + counter.to_bytes(8, "little"), digest_size=64).digest())
            counter += 1
        return bytes(out[:length])

    def aead_encrypt(
        self,
        key: bytes,
        plaintext: bytes,
        associated_data: Optional[bytes] = None,
        nonce: Optional[bytes] = None,
    ) -> Tuple[bytes, bytes]:
        nonce = self._resolve_nonce(nonce)
        keystream = self._stream(key, nonce, len(plaintext))
        body = bytes(a ^ b for a, b in zip(plaintext, keystream))
        ad = associated_data or b""
        tag = hmac.new(key, nonce + ad + body, hashlib.sha256).digest()
        return nonce, body + tag

    def aead_decrypt(
        self,
        key: bytes,
        ciphertext: bytes,
        nonce: bytes,
        associated_data: Optional[bytes] = None,
    ) -> bytes:
        self._resolve_nonce(nonce)
        if len(ciphertext) < 32:
            raise ValueError("ciphertext too short")
        body, tag = ciphertext[:-32], ciphertext[-32:]
        ad = associated_data or b""
        exp = hmac.new(key, nonce + ad + body, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, exp):
            raise ValueError("authentication failed")
        keystream = self._stream(key, nonce, len(body))
        return bytes(a ^ b for a, b in zip(body, keystream))

    def sign(self, private_key: bytes, message: bytes) -> bytes:
        return hmac.new(private_key, message, hashlib.sha256).digest()

    def verify(self, public_key: bytes, message: bytes, signature: bytes) -> bool:
        # For dev-only fallback we treat public_key as shared verifier key.
        exp = hmac.new(public_key, message, hashlib.sha256).digest()
        return hmac.compare_digest(exp, signature)


def _load_provider() -> _BaseProvider:
    try:
        return _SodiumProvider()
    except Exception:
        pass

    try:
        return _CryptographyProvider()
    except Exception:
        pass

    if os.getenv(_DEV_MODE_ENV, "").strip().lower() in {"1", "true", "yes", "on"}:
        return _InsecureDevProvider()

    raise INSECURE_CRYPTO_UNAVAILABLE(
        "No secure crypto backend found. Install PyNaCl (preferred) or cryptography. "
        f"Set {_DEV_MODE_ENV}=1 only for explicit development-mode fallback."
    )


_PROVIDER = _load_provider()
BACKEND_NAME = _PROVIDER.name
AEAD_NONCE_SIZE = _PROVIDER.nonce_size
SUPPORTS_SEALED_BOX = _PROVIDER.has_sealed_boxes


def random_bytes(length: int) -> bytes:
    return _PROVIDER.random_bytes(length)


def kdf(password: bytes | str, salt: bytes, length: int = 32) -> bytes:
    return _PROVIDER.kdf(password=password, salt=salt, length=length)


def aead_encrypt(
    key: bytes,
    plaintext: bytes,
    associated_data: Optional[bytes] = None,
    nonce: Optional[bytes] = None,
) -> Tuple[bytes, bytes]:
    return _PROVIDER.aead_encrypt(
        key=key,
        plaintext=plaintext,
        associated_data=associated_data,
        nonce=nonce,
    )


def aead_decrypt(
    key: bytes,
    ciphertext: bytes,
    nonce: bytes,
    associated_data: Optional[bytes] = None,
) -> bytes:
    return _PROVIDER.aead_decrypt(
        key=key,
        ciphertext=ciphertext,
        nonce=nonce,
        associated_data=associated_data,
    )


def sign(private_key: bytes, message: bytes) -> bytes:
    return _PROVIDER.sign(private_key=private_key, message=message)


def verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    return _PROVIDER.verify(public_key=public_key, message=message, signature=signature)


def seal_to_public_key(public_key: bytes, plaintext: bytes) -> bytes:
    return _PROVIDER.seal_to_public_key(public_key=public_key, plaintext=plaintext)


def open_sealed_box(public_key: bytes, private_key: bytes, sealed: bytes) -> bytes:
    return _PROVIDER.open_sealed_box(public_key=public_key, private_key=private_key, sealed=sealed)
=======
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
 main
