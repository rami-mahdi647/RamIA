import tempfile

import aichain
import crypto_backend
import ramia_core_secure


def test_crypto_backend_sign_verify_dev_roundtrip():
    sk = b"k" * 32
    pk = __import__("hashlib").sha256(sk).digest()
    msg = b"hello"
    sig = crypto_backend.sign(sk, msg)
    assert crypto_backend.verify(pk, msg, sig)
    assert not crypto_backend.verify(pk, b"tampered", sig)


def test_secure_adapter_rejects_unsigned_and_accepts_signed():
    with tempfile.TemporaryDirectory() as td:
        db = aichain.ChainDB(td)
        wallet_sk = b"s" * 32
        wallet_pk = __import__("hashlib").sha256(wallet_sk).digest()
        wallet = {
            "address": "genesis",
            "private_key": __import__("base64").urlsafe_b64encode(wallet_sk).decode().rstrip("="),
            "public_key": __import__("base64").urlsafe_b64encode(wallet_pk).decode().rstrip("="),
        }
        adapter = ramia_core_secure.SecureChainAdapter(db, wallet)

        unsigned = db.make_tx("genesis", "alice", 10_000, 1000, memo="u")
        ok, why = adapter.add_tx_to_mempool(unsigned)
        assert not ok
        assert why == "missing_signature"

        signed = adapter.make_tx("genesis", "alice", 10_000, 1000, memo="s")
        ok2, out2 = adapter.add_tx_to_mempool(signed)
        assert ok2
        assert out2 == signed.txid()


def test_canonical_payload_excludes_sig():
    tx = aichain.Transaction(
        version=1,
        vin=[aichain.TxIn(from_addr="genesis", sig="abc")],
        vout=[aichain.TxOut(to_addr="bob", amount=123)],
        fee=7,
        nonce=42,
        memo="m",
    )
    p1 = ramia_core_secure.canonical_signing_payload(tx)
    tx2 = aichain.Transaction(
        version=tx.version,
        vin=[aichain.TxIn(from_addr="genesis", sig="DIFFERENT")],
        vout=tx.vout,
        fee=tx.fee,
        nonce=tx.nonce,
        memo=tx.memo,
    )
    p2 = ramia_core_secure.canonical_signing_payload(tx2)
    assert p1 == p2
