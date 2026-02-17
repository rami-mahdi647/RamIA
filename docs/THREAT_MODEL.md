# RamIA Threat Model

This threat model maps concrete adversaries and failure modes to implementation touchpoints in:

- `wallet_secure.py`
- `crypto_backend.py`
- `tx_privacy.py`
- `ramia_core_secure.py`

## Assets

Primary assets to protect:

- wallet private signing keys,
- passphrases and derived key-encryption keys,
- encrypted wallet blobs and backup archives,
- transaction intent data before signing,
- anti-replay state (nonce/counter windows).

## Assumptions and boundaries

- The local host may be intermittently online and can be targeted by commodity malware.
- Network links are untrusted unless explicitly authenticated.
- Attackers can observe/modify traffic in transit but cannot break modern cryptography under correct use.
- Memory-safe operation is best effort in Python/runtime constraints; residual exposure exists.

## Threats and mitigations

## 1) Local device theft

### Scenario
Attacker steals a laptop/server disk containing wallet and backup files.

### Impact
Offline brute-force attempts against passphrase-protected wallet data.

### Mitigations

- `wallet_secure.py:create_wallet()` stores encrypted wallet material only.
- `crypto_backend.py:derive_kek()` applies a memory-hard KDF with per-wallet salt.
- `wallet_secure.py:export_encrypted_backup()` never emits plaintext exports.
- `ramia_core_secure.py:load_secure_wallet()` rejects malformed/legacy unencrypted formats by default.

### Residual risk
Weak passphrases remain vulnerable to offline guessing.

## 2) Malware on host

### Scenario
Malware executes under user context and attempts key exfiltration or transaction tampering.

### Impact
Possible theft if malware captures passphrase/keys during wallet unlock/signing.

### Mitigations

- `ramia_core_secure.py:boot_secure_runtime()` enforces least-privilege startup checks.
- `tx_privacy.py:build_signing_context()` canonicalizes and displays signing intent to reduce silent tampering.
- `wallet_secure.py:unlock_wallet()` minimizes plaintext key lifetime and avoids logging sensitive values.
- Operational controls in `SECURITY.md` require patched hosts, anti-malware, and isolated signer contexts.

### Residual risk
A sufficiently privileged runtime compromise can still capture secrets in-use.

## 3) Memory scraping

### Scenario
Adversary obtains memory snapshots through debugger access, crash dumps, swap leaks, or live scraping malware.

### Impact
Exposure of passphrase, decrypted keys, or derived session keys.

### Mitigations

- `wallet_secure.py:unlock_wallet()` avoids unnecessary copies and reduces secret lifetime.
- `ramia_core_secure.py:boot_secure_runtime()` should disable core dumps where feasible.
- `crypto_backend.py:decrypt_at_rest()` decrypts on-demand and returns scoped key material.

### Residual risk
Python and OS memory management may leave non-zeroized remnants; complete elimination is not guaranteed.

## 4) MITM (man-in-the-middle)

### Scenario
Attacker intercepts/modifies traffic between client and service endpoint.

### Impact
Injected transaction parameters, replayed requests, or downgraded security properties.

### Mitigations

- Enforce authenticated transport for remote operations.
- `tx_privacy.py:build_signing_context()` binds signed payloads to exact transaction fields.
- `ramia_core_secure.py:load_secure_wallet()` and request validation reject unauthenticated or malformed envelopes.

### Residual risk
If users approve maliciously altered intent due to UI confusion/social engineering, MITM defense can be bypassed at human layer.

## 5) Replay and spam

### Scenario
Attacker replays previously valid signed payloads or floods endpoints with nonce collisions.

### Impact
Duplicate actions, queue starvation, and potential fee/resource exhaustion.

### Mitigations

- `crypto_backend.py:allocate_nonce()` guarantees per-key nonce uniqueness.
- `tx_privacy.py:bind_nonce_to_tx()` records nonce use and rejects duplicates/replays.
- `ramia_core_secure.py:boot_secure_runtime()` enforces bounded timestamp skew and replay windows.

### Residual risk
High-volume spam can still impose availability pressure; rate limiting and queue controls remain necessary.

## 6) Nonce misuse and cryptographic misuse

### Scenario
Implementation bug reuses nonce or mixes key domains.

### Impact
Potential plaintext recovery, integrity failure, or signature confusion.

### Mitigations

- Strict primitive and parameter constraints in `docs/CRYPTO_SPEC.md`.
- `crypto_backend.py:allocate_nonce()` centralized nonce policy.
- `crypto_backend.py:derive_kek()` domain-separated key derivation labels.
- `ramia_core_secure.py:enforce_dev_mode_guardrails()` blocks insecure dev settings in production.

### Residual risk
Logic bugs are still possible; require tests, code review, and versioned migrations.

## Residual risk summary

Even with all controls:

- active host compromise during unlock/sign remains a high-impact event,
- weak operator passphrases materially reduce at-rest protection,
- availability attacks (spam/flood) cannot be solved by cryptography alone,
- side-channel and implementation defects are reduced, not eliminated.

Security posture depends on both correct implementation and disciplined operations.
