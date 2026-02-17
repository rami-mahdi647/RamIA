#!/usr/bin/env python3
"""Cryptography self-test for CI and local validation.

Checks:
- AEAD roundtrip
- nonce generation uniqueness policy
- Ed25519 sign/verify
- sealed-box roundtrip (if provider supports it)
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import secrets
import sys
from dataclasses import dataclass
from typing import Callable, List


@dataclass
class CheckResult:
    name: str
    passed: bool
    details: str
    skipped: bool = False


def print_result(r: CheckResult) -> None:
    status = "PASS" if r.passed else ("SKIP" if r.skipped else "FAIL")
    print(f"[{status}] {r.name}: {r.details}")


def has_module(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def check_aead_roundtrip() -> CheckResult:
    if not has_module("cryptography"):
        return CheckResult("AEAD roundtrip", False, "cryptography is not installed")

    ciphers = importlib.import_module("cryptography.hazmat.primitives.ciphers.aead")

    key = secrets.token_bytes(32)
    nonce = secrets.token_bytes(12)
    aad = b"ramia-selftest:aead"
    plaintext = b"ramia crypto self-test payload"

    algo = None
    if hasattr(ciphers, "ChaCha20Poly1305"):
        algo = ciphers.ChaCha20Poly1305(key)
        algo_name = "ChaCha20Poly1305"
    elif hasattr(ciphers, "AESGCM"):
        algo = ciphers.AESGCM(key)
        algo_name = "AESGCM"
    else:
        return CheckResult("AEAD roundtrip", False, "no AEAD provider available in cryptography")

    ciphertext = algo.encrypt(nonce, plaintext, aad)
    recovered = algo.decrypt(nonce, ciphertext, aad)

    if recovered != plaintext:
        return CheckResult("AEAD roundtrip", False, "decrypted plaintext does not match input")

    return CheckResult("AEAD roundtrip", True, f"{algo_name} encrypt/decrypt succeeded")


def generate_nonce() -> bytes:
    # 96-bit nonce policy for common AEAD constructions.
    return secrets.token_bytes(12)


def check_nonce_uniqueness() -> CheckResult:
    sample_size = 5000
    seen = set()

    for _ in range(sample_size):
        n = generate_nonce()
        if len(n) != 12:
            return CheckResult("Nonce uniqueness policy", False, f"invalid nonce length: {len(n)}")
        if n in seen:
            return CheckResult("Nonce uniqueness policy", False, "duplicate nonce generated")
        seen.add(n)

    if bytes(12) in seen:
        return CheckResult("Nonce uniqueness policy", False, "all-zero nonce generated")

    return CheckResult("Nonce uniqueness policy", True, f"{sample_size} nonces were unique and 96-bit")


def check_ed25519_sign_verify() -> CheckResult:
    if not has_module("cryptography"):
        return CheckResult("Ed25519 sign/verify", False, "cryptography is not installed")

    ed25519 = importlib.import_module("cryptography.hazmat.primitives.asymmetric.ed25519")

    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    message = b"ramia-selftest:ed25519"
    signature = private_key.sign(message)

    try:
        public_key.verify(signature, message)
    except Exception as exc:
        return CheckResult("Ed25519 sign/verify", False, f"verification failed: {exc}")

    return CheckResult("Ed25519 sign/verify", True, "signature verified successfully")


def check_sealed_box_roundtrip() -> CheckResult:
    if not has_module("nacl"):
        return CheckResult(
            "Sealed-box roundtrip",
            True,
            "PyNaCl unavailable; skipping sealed-box check",
            skipped=True,
        )

    nacl_public = importlib.import_module("nacl.public")

    recipient_sk = nacl_public.PrivateKey.generate()
    recipient_pk = recipient_sk.public_key

    sender_box = nacl_public.SealedBox(recipient_pk)
    recipient_box = nacl_public.SealedBox(recipient_sk)

    message = os.urandom(48)
    ciphertext = sender_box.encrypt(message)
    recovered = recipient_box.decrypt(ciphertext)

    if recovered != message:
        return CheckResult("Sealed-box roundtrip", False, "decrypted payload mismatch")

    return CheckResult("Sealed-box roundtrip", True, "encrypt/decrypt succeeded with PyNaCl SealedBox")


def main() -> int:
    checks: List[Callable[[], CheckResult]] = [
        check_aead_roundtrip,
        check_nonce_uniqueness,
        check_ed25519_sign_verify,
        check_sealed_box_roundtrip,
    ]

    results = [c() for c in checks]
    for r in results:
        print_result(r)

    failed = [r for r in results if not r.passed and not r.skipped]

    print("\nSummary:")
    print(f"  Total:  {len(results)}")
    print(f"  Passed: {sum(1 for r in results if r.passed and not r.skipped)}")
    print(f"  Skipped:{sum(1 for r in results if r.skipped)}")
    print(f"  Failed: {len(failed)}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
