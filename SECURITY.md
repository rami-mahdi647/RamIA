# Security Policy

This document defines the minimum security posture for RamIA wallet/key material, transaction signing, and secure runtime behavior.

## Scope and ownership

The controls in this file are implemented and/or enforced by:

- `wallet_secure.py`
  - `create_wallet()`
  - `unlock_wallet()`
  - `rotate_wallet_encryption_key()`
  - `export_encrypted_backup()`
- `crypto_backend.py`
  - `derive_kek()`
  - `encrypt_at_rest()`
  - `decrypt_at_rest()`
  - `allocate_nonce()`
- `tx_privacy.py`
  - `build_signing_context()`
  - `bind_nonce_to_tx()`
- `ramia_core_secure.py`
  - `boot_secure_runtime()`
  - `load_secure_wallet()`
  - `enforce_dev_mode_guardrails()`

> If code and this policy diverge, update both in the same PR.

## Wallet encryption at rest

- Private keys MUST never be stored plaintext on disk.
- `wallet_secure.py:create_wallet()` MUST serialize secrets only through `crypto_backend.py:encrypt_at_rest()`.
- Encryption-at-rest MUST use an AEAD mode with integrity protection (see `docs/CRYPTO_SPEC.md`).
- Wallet files MUST include metadata for:
  - key-derivation algorithm and parameters,
  - encryption algorithm version,
  - nonce/IV,
  - creation time and schema version.
- `ramia_core_secure.py:load_secure_wallet()` MUST reject wallet blobs missing required metadata.

## Passphrase policy

- Passphrases are required for interactive wallet creation/unlock in production mode.
- Minimum policy (enforced in `wallet_secure.py:unlock_wallet()`):
  - length >= 14 characters,
  - not present in a local/common denylist,
  - no leading/trailing whitespace ambiguity.
- High-privilege operators SHOULD use passphrases >= 18 characters.
- Passphrases MUST NOT be logged, echoed to debug output, or persisted to config files.
- Process-memory lifetime for passphrase bytes should be minimized; clear buffers where practical.

## Backup and rotation

- `wallet_secure.py:export_encrypted_backup()` MUST emit encrypted-only backups.
- Backups MUST be versioned and verifiable before deletion of prior generations.
- Keep at least:
  - 3 recent local encrypted backups,
  - 1 offline/offsite encrypted backup.
- `wallet_secure.py:rotate_wallet_encryption_key()` MUST support rewrapping wallet material under a new KEK without changing the signing keypair.
- Rotation cadence:
  - routine: every 90 days,
  - immediate: after any suspected credential exposure or host compromise.

## Nonce reuse dangers

- Nonce reuse with AEAD can catastrophically expose plaintext and/or permit forgery.
- `crypto_backend.py:allocate_nonce()` MUST guarantee uniqueness for a given key.
- `tx_privacy.py:bind_nonce_to_tx()` MUST bind nonce values to a transaction context and reject duplicates.
- Crash recovery MUST persist nonce counters/state before confirming writes that consume new nonces.

## Key separation and least privilege

- Separate keys by purpose; never reuse one key for multiple domains.
- Required separation:
  - wallet signing key (transaction authorization),
  - wallet encryption key (at-rest protection),
  - transport/session authentication key,
  - anti-replay/mac key (if applicable).
- `crypto_backend.py:derive_kek()` MUST use context labels/salts so derivations for different domains cannot collide.
- `ramia_core_secure.py:boot_secure_runtime()` MUST fail closed if key-separation labels are absent or malformed.

## Operational hardening

- Run secure components with least OS privileges.
- Enforce strict filesystem permissions on wallet and secret material (owner read/write only where supported).
- Enable full-disk encryption on operator devices and servers.
- Disable core dumps for processes handling plaintext keys/passphrases when feasible.
- Use host-level malware protection and keep OS/runtime dependencies patched.
- Prefer isolated execution contexts (dedicated user account/container/VM) for signer operations.
- `ramia_core_secure.py:enforce_dev_mode_guardrails()` MUST prevent accidental production startup with dev-mode crypto settings.

## Reporting a vulnerability

If you identify a vulnerability, report privately to project maintainers and include:

- affected module/function,
- exploit preconditions,
- impact scope,
- proof-of-concept steps (if safe),
- remediation recommendation.
