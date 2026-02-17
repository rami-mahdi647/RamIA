# RamIA Cryptography Specification

This specification defines approved cryptographic primitives, parameters, nonce rules, and migration/versioning behavior for:

- `wallet_secure.py`
- `crypto_backend.py`
- `tx_privacy.py`
- `ramia_core_secure.py`

## 1. Approved primitives

`crypto_backend.py` MUST restrict usage to approved algorithms only.

- Randomness:
  - CSPRNG from OS entropy source.
- Wallet encryption at rest:
  - AES-256-GCM **or** XChaCha20-Poly1305 (preferred where available).
- Key derivation from passphrase:
  - Argon2id (preferred).
  - PBKDF2-HMAC-SHA256 (compatibility mode only).
- Message authentication / context binding:
  - HMAC-SHA256 (where a standalone MAC is needed).
- Hashing:
  - SHA-256 for identifiers/checksums (non-password use).
- Signatures:
  - Ed25519 for wallet transaction signing.

Disallowed:

- MD5, SHA-1, unsalted fast password hashes,
- AES-CBC without robust authenticated wrapping,
- deterministic/static IV/nonce generation.

## 2. Parameter sizes and minimums

### 2.1 Symmetric encryption

- AES-GCM key size: 256 bits.
- XChaCha20-Poly1305 key size: 256 bits.
- Authentication tags must be full-length as defined by the primitive.

### 2.2 Nonce sizes

- AES-GCM nonce: 96 bits.
- XChaCha20-Poly1305 nonce: 192 bits.

Nonce format and source are controlled by `crypto_backend.py:allocate_nonce()`.

### 2.3 KDF parameters

#### Argon2id (default)

- memory cost: >= 64 MiB (target 128 MiB on server-grade hosts),
- time cost: >= 3 iterations,
- parallelism: 1-4 lanes depending on environment,
- salt length: >= 16 bytes (unique per wallet).

#### PBKDF2-HMAC-SHA256 (fallback/compat)

- iterations: >= 600,000,
- salt length: >= 16 bytes,
- derived key length: 32 bytes.

`crypto_backend.py:derive_kek()` MUST encode all parameters into wallet metadata.

## 3. Nonce and replay rules

- Nonces MUST be unique per `(key, algorithm)` pair.
- `crypto_backend.py:allocate_nonce()` MUST either:
  - use collision-resistant random nonces with collision monitoring, or
  - use persistent monotonic counters mapped to key IDs.
- `tx_privacy.py:bind_nonce_to_tx()` MUST bind nonce + tx digest + signer identity.
- Reused nonce with same key MUST be treated as a critical security fault and hard-fail.
- `ramia_core_secure.py:boot_secure_runtime()` MUST recover nonce state safely after restart before accepting signing/encryption requests.

## 4. Key separation and derivation domains

`crypto_backend.py:derive_kek()` MUST domain-separate derivations using explicit context labels.

Required derivation domains (example labels):

- `ramia.wallet.kek.v1`
- `ramia.backup.kek.v1`
- `ramia.transport.auth.v1`
- `ramia.replay.guard.v1`

No key generated for one domain may be reused in another domain.

## 5. Envelope format and metadata

Encrypted wallet/backup envelopes produced by `crypto_backend.py:encrypt_at_rest()` MUST include:

- `schema_version`,
- `crypto_suite` (e.g., `xchacha20poly1305+argon2id`),
- KDF parameters + salt,
- nonce,
- ciphertext,
- authentication tag (if separate field),
- optional key ID / creation timestamp.

`wallet_secure.py:unlock_wallet()` MUST validate metadata completeness and reject unknown mandatory fields unless explicitly allowed by migration policy.

## 6. Versioning and migration scheme

## 6.1 Version identifiers

- Envelope/schema versions are integer, monotonic (`v1`, `v2`, ...).
- `ramia_core_secure.py:load_secure_wallet()` MUST dispatch decoding by `schema_version`.

## 6.2 Migration flow

- Old versions may be read for migration if explicitly enabled.
- Migration writes MUST always output the current default version.
- Migration MUST be atomic:
  1. decrypt + verify old envelope,
  2. re-encrypt with new suite/params,
  3. write new file + fsync,
  4. replace old file.

## 6.3 Compatibility policy

- N-1 read compatibility SHOULD be maintained where practical.
- N-2 or older support MAY be removed with release-note warning.
- Any deprecated suite must emit warnings before removal.

## 7. Dev-mode behavior

`ramia_core_secure.py:enforce_dev_mode_guardrails()` governs development-only crypto relaxations.

Allowed in dev mode only:

- reduced KDF cost for local testing,
- ephemeral in-memory keys for disposable wallets,
- deterministic test vectors behind explicit test flags.

Never allowed (even in dev mode):

- plaintext private keys written to disk by default paths,
- disabled authentication tags/integrity checks,
- implicit fallback to broken/legacy primitives.

Production startup MUST fail if dev-mode crypto settings are detected unless an explicit, audited break-glass flag is provided.

## 8. Testing requirements (implementation alignment)

At minimum, tests should verify:

- nonce uniqueness under concurrency and restart,
- rejection on nonce reuse,
- KDF parameter enforcement and metadata persistence,
- migration correctness from prior schema versions,
- dev-mode guardrails blocking production boot.

These tests should target behavior exposed through:

- `wallet_secure.py:unlock_wallet()`
- `crypto_backend.py:allocate_nonce()`
- `crypto_backend.py:derive_kek()`
- `tx_privacy.py:bind_nonce_to_tx()`
- `ramia_core_secure.py:load_secure_wallet()`
