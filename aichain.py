#!/usr/bin/env python3
# AIChain: minimal ledger + PoW + dynamic issuance policy hook.
# Not production. Intended as a clean nucleus.

import argparse
import dataclasses
import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple


# ----------------------------
# Utilities
# ----------------------------

def sha256(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()

def hash_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def now_ts() -> int:
    return int(time.time())

def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


# ----------------------------
# Transaction (simple account model)
# ----------------------------

@dataclasses.dataclass(frozen=True)
class TxIn:
    # For a real system: signatures, prevouts, scripts, etc.
    # Here: "from_addr" is a string identifier; "sig" is placeholder.
    from_addr: str
    sig: str = ""

@dataclasses.dataclass(frozen=True)
class TxOut:
    to_addr: str
    amount: int  # atomic units

@dataclasses.dataclass(frozen=True)
class Transaction:
    version: int
    vin: List[TxIn]
    vout: List[TxOut]
    fee: int
    nonce: int
    memo: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "vin": [dataclasses.asdict(i) for i in self.vin],
            "vout": [dataclasses.asdict(o) for o in self.vout],
            "fee": self.fee,
            "nonce": self.nonce,
            "memo": self.memo,
        }

    def txid(self) -> str:
        return hash_hex(canonical_json(self.to_dict()))


# ----------------------------
# Block
# ----------------------------

@dataclasses.dataclass(frozen=True)
class BlockHeader:
    version: int
    prev_hash: str
    merkle_root: str
    timestamp: int
    height: int
    bits: int     # difficulty as leading hex zeros target
    nonce: int

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    def hash(self) -> str:
        return hash_hex(canonical_json(self.to_dict()))

@dataclasses.dataclass(frozen=True)
class Block:
    header: BlockHeader
    txs: List[Transaction]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "header": self.header.to_dict(),
            "txs": [t.to_dict() for t in self.txs],
        }

    def block_hash(self) -> str:
        return self.header.hash()


def merkle_root(txids: List[str]) -> str:
    if not txids:
        return hash_hex(b"")
    layer = [bytes.fromhex(t) for t in txids]
    while len(layer) > 1:
        if len(layer) % 2 == 1:
            layer.append(layer[-1])
        nxt = []
        for i in range(0, len(layer), 2):
            nxt.append(sha256(layer[i] + layer[i + 1]))
        layer = nxt
    return layer[0].hex()


# ----------------------------
# "AI" policy: dynamic issuance
# ----------------------------

class IssuancePolicy:
    """
    Replace this with a real model later.
    This is an online-updated linear policy with bounded output.
    Input features are chain/network metrics you can later source from P2P.
    """

    def __init__(self, base_subsidy: int, min_subsidy: int, max_subsidy: int):
        self.base = base_subsidy
        self.min = min_subsidy
        self.max = max_subsidy

        # weights: [miners, nodes, tx_count, mempool_size, fee_pressure]
        self.w = [0.0, 0.0, 0.0, 0.0, 0.0]
        self.lr = 1e-4

    def predict(self, miners: int, nodes: int, tx_count: int, mempool_size: int, fee_pressure: float) -> int:
        x = [float(miners), float(nodes), float(tx_count), float(mempool_size), float(fee_pressure)]
        s = self.base
        for wi, xi in zip(self.w, x):
            s += wi * xi
        s = int(round(s))
        if s < self.min:
            s = self.min
        if s > self.max:
            s = self.max
        return s

    def update(self, x: Tuple[int, int, int, int, float], target_subsidy: int):
        # Optional: you can define "target_subsidy" by a rule,
        # or ignore updates and keep it static.
        miners, nodes, tx_count, mempool_size, fee_pressure = x
        pred = self.predict(miners, nodes, tx_count, mempool_size, fee_pressure)
        err = float(target_subsidy - pred)
        feats = [float(miners), float(nodes), float(tx_count), float(mempool_size), float(fee_pressure)]
        for i in range(len(self.w)):
            self.w[i] += self.lr * err * feats[i]


# ----------------------------
# Chain state (minimal)
# ----------------------------

class ChainDB:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(self.path, exist_ok=True)
        self.blocks_path = os.path.join(self.path, "blocks.jsonl")
        self.state_path = os.path.join(self.path, "state.json")

        self.blocks: List[Block] = []
        self.balances: Dict[str, int] = {}
        self.mempool: Dict[str, Transaction] = {}

        self.bits = 5  # leading hex zeros requirement; simplistic
        self.target_block_time = 60  # seconds

        self.policy = IssuancePolicy(
            base_subsidy=50_000_000,  # atomic units (like satoshis)
            min_subsidy=1_000_000,
            max_subsidy=200_000_000,
        )

        self._load()

        if not self.blocks:
            self._genesis()

    def _load(self):
        if os.path.exists(self.blocks_path):
            with open(self.blocks_path, "r", encoding="utf-8") as f:
                for line in f:
                    obj = json.loads(line)
                    hdr = BlockHeader(**obj["header"])
                    txs = []
                    for t in obj["txs"]:
                        vin = [TxIn(**i) for i in t["vin"]]
                        vout = [TxOut(**o) for o in t["vout"]]
                        txs.append(Transaction(
                            version=t["version"], vin=vin, vout=vout,
                            fee=t["fee"], nonce=t["nonce"], memo=t.get("memo", "")
                        ))
                    self.blocks.append(Block(header=hdr, txs=txs))

        if os.path.exists(self.state_path):
            with open(self.state_path, "r", encoding="utf-8") as f:
                st = json.loads(f.read())
                self.balances = {k: int(v) for k, v in st.get("balances", {}).items()}
                self.bits = int(st.get("bits", self.bits))

    def _persist_block(self, blk: Block):
        with open(self.blocks_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(blk.to_dict(), sort_keys=True) + "\n")

    def _persist_state(self):
        st = {"balances": self.balances, "bits": self.bits}
        with open(self.state_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(st, sort_keys=True, indent=2))

    def _genesis(self):
        coinbase = Transaction(
            version=1,
            vin=[TxIn(from_addr="COINBASE")],
            vout=[TxOut(to_addr="genesis", amount=100_000_000_000)],
            fee=0,
            nonce=0,
            memo="genesis",
        )
        txids = [coinbase.txid()]
        mr = merkle_root(txids)
        hdr = BlockHeader(
            version=1,
            prev_hash="00" * 32,
            merkle_root=mr,
            timestamp=now_ts(),
            height=0,
            bits=self.bits,
            nonce=0,
        )
        blk = Block(header=hdr, txs=[coinbase])
        # mine genesis quickly
        blk = self._mine_block(blk)
        self._apply_block(blk)
        self.blocks.append(blk)
        self._persist_block(blk)
        self._persist_state()

    def tip(self) -> Block:
        return self.blocks[-1]

    def height(self) -> int:
        return self.tip().header.height

    # ----------------------------
    # Validation
    # ----------------------------

    def _check_pow(self, hdr: BlockHeader) -> bool:
        h = hdr.hash()
        return h.startswith("0" * hdr.bits)

    def _verify_tx_basic(self, tx: Transaction) -> Tuple[bool, str]:
        if tx.fee < 0:
            return False, "negative fee"
        if tx.version != 1:
            return False, "unsupported tx version"
        if len(tx.vout) == 0:
            return False, "no outputs"
        for o in tx.vout:
            if o.amount <= 0:
                return False, "nonpositive output"
            if not o.to_addr:
                return False, "empty to_addr"
        # Signature verification intentionally not implemented here.
        # Define a signature scheme and enforce it in production.
        return True, "ok"

    def _sum_outputs(self, tx: Transaction) -> int:
        return sum(o.amount for o in tx.vout)

    def _sender(self, tx: Transaction) -> Optional[str]:
        # single-sender simplification
        if not tx.vin:
            return None
        if len(tx.vin) != 1:
            return None
        return tx.vin[0].from_addr

    def _is_coinbase(self, tx: Transaction) -> bool:
        return len(tx.vin) == 1 and tx.vin[0].from_addr == "COINBASE"

    def _verify_block(self, blk: Block) -> Tuple[bool, str]:
        hdr = blk.header
        if hdr.height != self.height() + 1:
            return False, "bad height"
        if hdr.prev_hash != self.tip().block_hash():
            return False, "bad prev_hash"
        if hdr.timestamp < self.tip().header.timestamp:
            return False, "time went backwards"
        if hdr.bits != self.bits:
            return False, "unexpected difficulty bits"
        if not self._check_pow(hdr):
            return False, "bad PoW"

        txids = [t.txid() for t in blk.txs]
        if merkle_root(txids) != hdr.merkle_root:
            return False, "bad merkle root"

        if not blk.txs:
            return False, "empty block"
        if not self._is_coinbase(blk.txs[0]):
            return False, "first tx must be coinbase"

        # basic tx checks
        for t in blk.txs:
            ok, why = self._verify_tx_basic(t)
            if not ok:
                return False, f"tx invalid: {why}"

        # accounting checks
        fees = sum(t.fee for t in blk.txs[1:])
        coinbase_out = self._sum_outputs(blk.txs[0])

        # network metrics stub — replace with real-time P2P metrics later
        miners = 100
        nodes = 200
        tx_count = len(blk.txs) - 1
        mempool_size = len(self.mempool)
        fee_pressure = float(fees) / max(1.0, float(tx_count))

        subsidy = self.policy.predict(miners, nodes, tx_count, mempool_size, fee_pressure)
        max_coinbase = subsidy + fees

        if coinbase_out > max_coinbase:
            return False, "coinbase pays too much"

        return True, "ok"

    # ----------------------------
    # State transition
    # ----------------------------

    def _apply_tx(self, tx: Transaction) -> Tuple[bool, str]:
        if self._is_coinbase(tx):
            for o in tx.vout:
                self.balances[o.to_addr] = self.balances.get(o.to_addr, 0) + o.amount
            return True, "ok"

        sender = self._sender(tx)
        if not sender:
            return False, "unsupported vin"
        spend = self._sum_outputs(tx) + tx.fee
        bal = self.balances.get(sender, 0)
        if bal < spend:
            return False, "insufficient funds"
        self.balances[sender] = bal - spend
        for o in tx.vout:
            self.balances[o.to_addr] = self.balances.get(o.to_addr, 0) + o.amount
        return True, "ok"

    def _apply_block(self, blk: Block) -> Tuple[bool, str]:
        # apply all txs in order; no reorg logic here
        snap = dict(self.balances)
        for t in blk.txs:
            ok, why = self._apply_tx(t)
            if not ok:
                self.balances = snap
                return False, f"apply failed: {why}"
        return True, "ok"

    # ----------------------------
    # Mining & difficulty adjustment (simple)
    # ----------------------------

    def _adjust_difficulty(self):
        # naive: every 10 blocks look at actual time vs target
        if self.height() < 10:
            return
        window = 10
        tip = self.tip()
        past = self.blocks[-window]
        actual = tip.header.timestamp - past.header.timestamp
        target = window * self.target_block_time
        if actual < max(1, target // 2):
            self.bits = min(64, self.bits + 1)
        elif actual > target * 2:
            self.bits = max(1, self.bits - 1)

    def _mine_block(self, blk: Block) -> Block:
        hdr = blk.header
        nonce = 0
        while True:
            nh = dataclasses.replace(hdr, nonce=nonce)
            if self._check_pow(nh):
                return Block(header=nh, txs=blk.txs)
            nonce += 1

    def build_block_template(self, miner_addr: str) -> Block:
        self._adjust_difficulty()

        txs = list(self.mempool.values())

        fees = sum(t.fee for t in txs)
        tx_count = len(txs)
        miners = 100
        nodes = 200
        mempool_size = len(self.mempool)
        fee_pressure = float(fees) / max(1.0, float(tx_count))

        subsidy = self.policy.predict(miners, nodes, tx_count, mempool_size, fee_pressure)

        coinbase = Transaction(
            version=1,
            vin=[TxIn(from_addr="COINBASE")],
            vout=[TxOut(to_addr=miner_addr, amount=subsidy + fees)],
            fee=0,
            nonce=int.from_bytes(os.urandom(4), "big"),
            memo="coinbase",
        )

        all_txs = [coinbase] + txs
        txids = [t.txid() for t in all_txs]
        mr = merkle_root(txids)

        hdr = BlockHeader(
            version=1,
            prev_hash=self.tip().block_hash(),
            merkle_root=mr,
            timestamp=now_ts(),
            height=self.height() + 1,
            bits=self.bits,
            nonce=0,
        )
        return Block(header=hdr, txs=all_txs)

    def submit_block(self, blk: Block) -> Tuple[bool, str]:
        ok, why = self._verify_block(blk)
        if not ok:
            return False, why
        ok2, why2 = self._apply_block(blk)
        if not ok2:
            return False, why2

        self.blocks.append(blk)
        self._persist_block(blk)
        self._persist_state()

        # remove included txs from mempool
        for t in blk.txs[1:]:
            self.mempool.pop(t.txid(), None)
        return True, "accepted"

    def add_tx_to_mempool(self, tx: Transaction) -> Tuple[bool, str]:
        ok, why = self._verify_tx_basic(tx)
        if not ok:
            return False, why
        txid = tx.txid()
        if txid in self.mempool:
            return False, "already in mempool"
        self.mempool[txid] = tx
        return True, txid

    # ----------------------------
    # Simple wallet-ish helpers (toy)
    # ----------------------------

    def make_tx(self, from_addr: str, to_addr: str, amount: int, fee: int, memo: str = "") -> Transaction:
        # no signature; placeholder
        return Transaction(
            version=1,
            vin=[TxIn(from_addr=from_addr, sig="")],
            vout=[TxOut(to_addr=to_addr, amount=amount)],
            fee=fee,
            nonce=int.from_bytes(os.urandom(4), "big"),
            memo=memo,
        )


# ----------------------------
# CLI
# ----------------------------

def cmd_init(args):
    db = ChainDB(args.datadir)
    print("ok")
    print("height", db.height())
    print("tip", db.tip().block_hash())

def cmd_balance(args):
    db = ChainDB(args.datadir)
    print(db.balances.get(args.addr, 0))

def cmd_send(args):
    db = ChainDB(args.datadir)
    tx = db.make_tx(args.from_addr, args.to_addr, args.amount, args.fee, memo=args.memo)
    ok, out = db.add_tx_to_mempool(tx)
    if not ok:
        print("error", out)
        return
    print("txid", out)

def cmd_mine(args):
    db = ChainDB(args.datadir)
    tpl = db.build_block_template(args.miner_addr)
    mined = db._mine_block(tpl)
    ok, why = db.submit_block(mined)
    if not ok:
        print("error", why)
        return
    print("ok accepted")
    print("height", db.height())
    print("hash", mined.block_hash())
    print("coinbase_paid", sum(o.amount for o in mined.txs[0].vout))

def cmd_chain(args):
    db = ChainDB(args.datadir)
    for b in db.blocks[-args.n:]:
        print(b.header.height, b.block_hash(), b.header.timestamp, "txs", len(b.txs), "bits", b.header.bits)

def main():
    p = argparse.ArgumentParser(prog="aichain")
    p.add_argument("--datadir", default="./aichain_data")
    sp = p.add_subparsers(dest="cmd", required=True)

    s0 = sp.add_parser("init")
    s0.set_defaults(func=cmd_init)

    s1 = sp.add_parser("balance")
    s1.add_argument("addr")
    s1.set_defaults(func=cmd_balance)

    s2 = sp.add_parser("send")
    s2.add_argument("from_addr")
    s2.add_argument("to_addr")
    s2.add_argument("amount", type=int)
    s2.add_argument("--fee", type=int, default=1000)
    s2.add_argument("--memo", default="")
    s2.set_defaults(func=cmd_send)

    s3 = sp.add_parser("mine")
    s3.add_argument("miner_addr")
    s3.set_defaults(func=cmd_mine)

    s4 = sp.add_parser("chain")
    s4.add_argument("--n", type=int, default=20)
    s4.set_defaults(func=cmd_chain)

    args = p.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
