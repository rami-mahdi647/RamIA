#!/usr/bin/env python3
"""
ramia_wallet_secure.py

Terminal-first secure-ish wallet file for RamIA prototype.
- Generates a new private key using secrets (CSPRNG)
- Encrypts wallet at rest with AES-256-GCM (pure stdlib implementation via OpenSSL? NO)
  -> We DO NOT have AES-GCM in Python stdlib.
So we implement a robust alternative using:
- scrypt KDF (hashlib.scrypt) + HMAC-SHA256 for integrity + XOR stream cipher from HKDF-like PRF

IMPORTANT:
- This is a pragmatic, dependency-free "encrypted container" for prototypes.
- For production: use audited crypto (libsodium/cryptography) + standard key derivation formats.

Design:
- master_key = scrypt(passphrase, salt, n=2**14, r=8, p=1, dklen=64)
- enc_key = master_key[:32]
- mac_key = master_key[32:]
- keystream = HMAC(enc_key, nonce||counter) blocks -> XOR with plaintext (stream encryption)
- tag = HMAC(mac_key, header||ciphertext)
- Decrypt verifies tag before decrypting.
- Private key is never printed by default.

Commands:
  create  --out wallet.secure.json --label "rami"
  info    --wallet wallet.secure.json
  export-pub --wallet wallet.secure.json --out wallet_public.json
  decrypt --wallet wallet.secure.json  (prints private key ONLY if --danger-print-private is set)

This wallet format is self-contained and portable (keep file + passphrase).
"""

import argparse
import base64
import getpass
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
from dataclasses import dataclass
from typing import Dict, Tuple

WALLET_VERSION = 1

# --- helpers ---

def b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")

def b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)

def sha256(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()

def hmac_sha256(key: bytes, msg: bytes) -> bytes:
    return hmac.new(key, msg, hashlib.sha256).digest()

def scrypt_kdf(passphrase: str, salt: bytes, dklen: int = 64) -> bytes:
    # Parameters chosen to be "reasonable" for mobile and dev machines.
    # Increase N for stronger resistance if performance allows.
    return hashlib.scrypt(
        passphrase.encode("utf-8"),
        salt=salt,
        n=2**14,  # CPU/memory cost
        r=8,
        p=1,
        dklen=dklen,
    )

def prf_keystream(enc_key: bytes, nonce: bytes, length: int) -> bytes:
    # Derive keystream blocks with HMAC(enc_key, nonce||counter)
    out = bytearray()
    counter = 0
    while len(out) < length:
        counter_bytes = counter.to_bytes(8, "big")
        out.extend(hmac_sha256(enc_key, nonce + counter_bytes))
        counter += 1
    return bytes(out[:length])

def xor_bytes(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))

def normalize_passphrase(p: str) -> str:
    # Avoid accidental trailing spaces
    return p.strip()

def ensure_0600(path: str) -> None:
    # Best-effort on Unix-like
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass

# --- wallet model ---

@dataclass
class WalletSecrets:
    privkey: bytes  # 32 bytes

def generate_privkey() -> bytes:
    return secrets.token_bytes(32)

def derive_pubkey_simulated(privkey: bytes) -> bytes:
    """
    Placeholder "public key" derivation for prototype.
    Replace with proper Ed25519/secp256k1 when you add audited crypto libs.

    For now we compute pubkey = SHA256("RAMIA-PUB" || privkey)
    """
    return sha256(b"RAMIA-PUB" + privkey)

def derive_address(pubkey: bytes) -> str:
    """
    Prototype address: ramia1 + base64url(sha256(pubkey))[:24]
    """
    h = sha256(pubkey)
    return "ramia1" + b64e(h)[:24]

def encrypt_wallet(secrets_obj: WalletSecrets, passphrase: str, label: str) -> Dict:
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(16)
    master = scrypt_kdf(passphrase, salt, dklen=64)
    enc_key = master[:32]
    mac_key = master[32:]

    pubkey = derive_pubkey_simulated(secrets_obj.privkey)
    address = derive_address(pubkey)

    payload = {
        "label": label,
        "created_at": int(time.time()),
        "privkey": b64e(secrets_obj.privkey),
        "pubkey": b64e(pubkey),
        "address": address,
    }
    plaintext = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    keystream = prf_keystream(enc_key, nonce, len(plaintext))
    ciphertext = xor_bytes(plaintext, keystream)

    header = {
        "format": "ramia_wallet_secure",
        "version": WALLET_VERSION,
        "kdf": "scrypt",
        "kdf_params": {"n": 2**14, "r": 8, "p": 1, "dklen": 64},
        "salt": b64e(salt),
        "nonce": b64e(nonce),
    }
    header_bytes = json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")
    tag = hmac_sha256(mac_key, header_bytes + ciphertext)

    return {
        "header": header,
        "ciphertext": b64e(ciphertext),
        "tag": b64e(tag),
    }

def decrypt_wallet(wallet_doc: Dict, passphrase: str) -> Dict:
    header = wallet_doc["header"]
    salt = b64d(header["salt"])
    nonce = b64d(header["nonce"])
    ciphertext = b64d(wallet_doc["ciphertext"])
    tag = b64d(wallet_doc["tag"])

    master = scrypt_kdf(passphrase, salt, dklen=64)
    enc_key = master[:32]
    mac_key = master[32:]

    header_bytes = json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")
    expected_tag = hmac_sha256(mac_key, header_bytes + ciphertext)
    if not hmac.compare_digest(expected_tag, tag):
        raise ValueError("Bad passphrase or corrupted wallet (MAC check failed).")

    keystream = prf_keystream(enc_key, nonce, len(ciphertext))
    plaintext = xor_bytes(ciphertext, keystream)
    payload = json.loads(plaintext.decode("utf-8"))
    return payload

# --- CLI ---

def cmd_create(args: argparse.Namespace) -> int:
    label = args.label or "ramia_wallet"
    out_path = args.out

    pass1 = normalize_passphrase(getpass.getpass("Choose a wallet passphrase: "))
    pass2 = normalize_passphrase(getpass.getpass("Repeat passphrase: "))
    if pass1 != pass2:
        print("ERROR: Passphrases do not match.", file=sys.stderr)
        return 2
    if len(pass1) < 10:
        print("ERROR: Passphrase too short. Use at least 10 characters.", file=sys.stderr)
        return 2

    priv = generate_privkey()
    doc = encrypt_wallet(WalletSecrets(privkey=priv), pass1, label)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, sort_keys=True)
    ensure_0600(out_path)

    # Print ONLY safe info
    payload = decrypt_wallet(doc, pass1)
    print("ok")
    print("wallet_file", out_path)
    print("address", payload["address"])
    print("pubkey", payload["pubkey"])
    return 0

def cmd_info(args: argparse.Namespace) -> int:
    with open(args.wallet, "r", encoding="utf-8") as f:
        doc = json.load(f)
    pw = normalize_passphrase(getpass.getpass("Wallet passphrase: "))
    payload = decrypt_wallet(doc, pw)
    # safe info only
    print("ok")
    print("label", payload.get("label", ""))
    print("created_at", payload.get("created_at", 0))
    print("address", payload.get("address", ""))
    print("pubkey", payload.get("pubkey", ""))
    return 0

def cmd_export_pub(args: argparse.Namespace) -> int:
    with open(args.wallet, "r", encoding="utf-8") as f:
        doc = json.load(f)
    pw = normalize_passphrase(getpass.getpass("Wallet passphrase: "))
    payload = decrypt_wallet(doc, pw)
    pub = {
        "label": payload.get("label", ""),
        "address": payload.get("address", ""),
        "pubkey": payload.get("pubkey", ""),
        "created_at": payload.get("created_at", 0),
        "format": "ramia_wallet_public",
        "version": WALLET_VERSION,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(pub, f, indent=2, sort_keys=True)
    print("ok")
    print("public_wallet_file", args.out)
    print("address", pub["address"])
    return 0

def cmd_decrypt(args: argparse.Namespace) -> int:
    with open(args.wallet, "r", encoding="utf-8") as f:
        doc = json.load(f)
    pw = normalize_passphrase(getpass.getpass("Wallet passphrase: "))
    payload = decrypt_wallet(doc, pw)
    print("ok")
    print("address", payload.get("address", ""))
    print("pubkey", payload.get("pubkey", ""))
    if args.danger_print_private:
        print("PRIVATE_KEY_B64", payload.get("privkey", ""))
    else:
        print("note", "Private key not printed. Use --danger-print-private to display it (NOT recommended).")
    return 0

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ramia_wallet_secure.py", description="RamIA prototype secure wallet (no private-key printing by default).")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("create", help="Create a new encrypted wallet file")
    c.add_argument("--out", required=True, help="Output wallet file path (e.g., wallet.secure.json)")
    c.add_argument("--label", default="ramia_wallet", help="Wallet label")
    c.set_defaults(func=cmd_create)

    i = sub.add_parser("info", help="Show wallet public info (requires passphrase)")
    i.add_argument("--wallet", required=True, help="Wallet file path")
    i.set_defaults(func=cmd_info)

    e = sub.add_parser("export-pub", help="Export public wallet info JSON")
    e.add_argument("--wallet", required=True, help="Wallet file path")
    e.add_argument("--out", required=True, help="Output public file path")
    e.set_defaults(func=cmd_export_pub)

    d = sub.add_parser("decrypt", help="Decrypt wallet (prints private key only with --danger-print-private)")
    d.add_argument("--wallet", required=True, help="Wallet file path")
    d.add_argument("--danger-print-private", action="store_true", help="Print private key (NOT recommended)")
    d.set_defaults(func=cmd_decrypt)

    return p

def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)

if __name__ == "__main__":
    raise SystemExit(main())
