#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import hmac
import json
import os
import secrets
import stat
from dataclasses import dataclass
from typing import Any, Dict

HAVE_CRYPTO = True
try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except Exception:
    HAVE_CRYPTO = False


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64d(text: str) -> bytes:
    pad = "=" * ((4 - (len(text) % 4)) % 4)
    return base64.urlsafe_b64decode((text + pad).encode("utf-8"))


def _chmod_600_best_effort(path: str) -> None:
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass


def _atomic_write_json(path: str, obj: Dict[str, Any]) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False, indent=2))
        fh.write("\n")
    os.replace(tmp, path)
    _chmod_600_best_effort(path)


@dataclass
class KDFMaterial:
    config: Dict[str, Any]
    key: bytes


def _derive_key(passphrase: str, salt: bytes) -> KDFMaterial:
    password = passphrase.encode("utf-8")
    try:
        from argon2.low_level import hash_secret_raw, Type  # type: ignore

        key = hash_secret_raw(password, salt, 3, 65536, 1, 32, Type.ID)
        return KDFMaterial({"name": "argon2id", "salt": _b64e(salt), "time_cost": 3, "memory_cost": 65536, "parallelism": 1, "key_len": 32}, key)
    except Exception:
        pass

    try:
        n, r, p = 1 << 15, 8, 1
        key = hashlib.scrypt(password, salt=salt, n=n, r=r, p=p, dklen=32)
        return KDFMaterial({"name": "scrypt", "salt": _b64e(salt), "n": n, "r": r, "p": p, "key_len": 32}, key)
    except Exception:
        pass

    iterations = 600_000
    key = hashlib.pbkdf2_hmac("sha256", password, salt, iterations, dklen=32)
    return KDFMaterial({"name": "pbkdf2_sha256", "salt": _b64e(salt), "iterations": iterations, "key_len": 32}, key)


def _derive_key_from_config(passphrase: str, kdf: Dict[str, Any]) -> bytes:
    salt = _b64d(str(kdf["salt"]))
    password = passphrase.encode("utf-8")
    name = str(kdf.get("name", ""))

    if name == "argon2id":
        from argon2.low_level import hash_secret_raw, Type  # type: ignore

        return hash_secret_raw(password, salt, int(kdf["time_cost"]), int(kdf["memory_cost"]), int(kdf["parallelism"]), int(kdf.get("key_len", 32)), Type.ID)
    if name == "scrypt":
        return hashlib.scrypt(password, salt=salt, n=int(kdf["n"]), r=int(kdf["r"]), p=int(kdf["p"]), dklen=int(kdf.get("key_len", 32)))
    if name == "pbkdf2_sha256":
        return hashlib.pbkdf2_hmac("sha256", password, salt, int(kdf["iterations"]), dklen=int(kdf.get("key_len", 32)))
    raise ValueError(f"unsupported_kdf:{name}")


def _keystream(key: bytes, nonce: bytes, aad: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        blk = hmac.new(key, nonce + counter.to_bytes(8, "big") + aad, hashlib.sha256).digest()
        out.extend(blk)
        counter += 1
    return bytes(out[:length])


def _aead_encrypt(key: bytes, nonce: bytes, plaintext: bytes, aad: bytes) -> Dict[str, Any]:
    if HAVE_CRYPTO:
        ct = AESGCM(key).encrypt(nonce, plaintext, aad)
        return {"name": "aes-256-gcm", "nonce": _b64e(nonce), "aad": _b64e(aad), "ciphertext": _b64e(ct)}

    stream = _keystream(key, nonce, aad, len(plaintext))
    body = bytes(a ^ b for a, b in zip(plaintext, stream))
    tag = hmac.new(key, nonce + aad + body, hashlib.sha256).digest()
    return {"name": "hmac-sha256-stream-v1", "nonce": _b64e(nonce), "aad": _b64e(aad), "ciphertext": _b64e(body + tag)}


def _address_from_pub(pub: bytes) -> str:
    return hashlib.sha256(pub).hexdigest()[:40]


def _new_signing_material() -> Dict[str, Any]:
    if HAVE_CRYPTO:
        sk = Ed25519PrivateKey.generate()
        pk = sk.public_key()
        sk_bytes = sk.private_bytes(encoding=serialization.Encoding.Raw, format=serialization.PrivateFormat.Raw, encryption_algorithm=serialization.NoEncryption())
        pk_bytes = pk.public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
        return {"type": "ed25519", "private": sk_bytes, "public": pk_bytes}

    priv = secrets.token_bytes(32)
    pub = hashlib.sha256(priv).digest()
    return {"type": "dev_signing_key", "private": priv, "public": pub}


def create_wallet_file(out_path: str, label: str = "default") -> Dict[str, Any]:
    p1 = getpass.getpass("Passphrase: ")
    p2 = getpass.getpass("Confirm passphrase: ")
    if p1 != p2:
        raise ValueError("passphrase_mismatch")
    if len(p1) < 10:
        raise ValueError("passphrase_too_short")

    km = _new_signing_material()
    salt = secrets.token_bytes(16)
    kdf = _derive_key(p1, salt)
    nonce = secrets.token_bytes(12)

    public_identity = {"address": _address_from_pub(km["public"]), "public_key": _b64e(km["public"]), "curve": km["type"], "label": label}
    aad = json.dumps({"v": 1, "public": public_identity}, sort_keys=True).encode("utf-8")

    wallet = {
        "metadata": {"version": 1, "format": "ramia.wallet.secure"},
        "kdf": kdf.config,
        "aead": _aead_encrypt(kdf.key, nonce, km["private"], aad),
        "public": public_identity,
    }
    _atomic_write_json(out_path, wallet)
    return wallet


def load_wallet(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.loads(fh.read())


def public_identity_only(wallet: Dict[str, Any]) -> Dict[str, Any]:
    public = dict(wallet.get("public", {}))
    return {"version": wallet.get("metadata", {}).get("version", 1), "type": "secure_wallet", "label": public.get("label"), "address": public.get("address"), "public_key": public.get("public_key")}


def load_public_identity_compat(wallet_path: str) -> Dict[str, Any]:
    return public_identity_only(load_wallet(wallet_path))


def _kdf_info(kdf: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in kdf.items() if k != "salt"}
    out["salt_present"] = "salt" in kdf
    return out


def cmd_create(args: argparse.Namespace) -> int:
    w = create_wallet_file(args.out, label=args.label)
    print(json.dumps({"ok": True, "wallet": public_identity_only(w), "out": args.out}, indent=2))
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    wallet = load_wallet(args.wallet)
    out = {
        "ok": True,
        "wallet": args.wallet,
        "metadata": wallet.get("metadata", {}),
        "kdf": _kdf_info(wallet.get("kdf", {})),
        "aead": {"name": wallet.get("aead", {}).get("name"), "nonce_present": bool(wallet.get("aead", {}).get("nonce")), "ciphertext_len": len(wallet.get("aead", {}).get("ciphertext", ""))},
        "public": wallet.get("public", {}),
    }
    print(json.dumps(out, indent=2))
    return 0


def cmd_export_pub(args: argparse.Namespace) -> int:
    wallet = load_wallet(args.wallet)
    print(json.dumps({"ok": True, "address": wallet.get("public", {}).get("address"), "public_key": wallet.get("public", {}).get("public_key")}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Secure wallet file utility")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("create", help="Create secure wallet file")
    c.add_argument("--out", default="wallet.secure.json")
    c.add_argument("--label", default="default")
    c.set_defaults(func=cmd_create)

    i = sub.add_parser("info", help="Show non-sensitive wallet information")
    i.add_argument("--wallet", required=True)
    i.set_defaults(func=cmd_info)

    e = sub.add_parser("export-pub", help="Export public key/address only")
    e.add_argument("--wallet", required=True)
    e.set_defaults(func=cmd_export_pub)
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
