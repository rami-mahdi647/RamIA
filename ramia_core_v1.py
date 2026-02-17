#!/usr/bin/env python3
"""RamIA tokenomics v1 entrypoint.

Wraps existing aichain module without editing its core logic.
Adds a deterministic post-template emission transaction and tracks
remaining emission pool in datadir/token_state.json.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from typing import Any, Dict

import aichain
import tokenomics_v1

EMISSION_POOL_TOTAL = tokenomics_v1.allocation_table()["community"] + tokenomics_v1.allocation_table()["market_incentives"]
EPOCH_LENGTH_SEC = 86_400


@dataclass
class TokenState:
    emission_pool_total: int
    remaining_pool: int
    minted_total: int
    epoch_length_sec: int
    genesis_ts: int
    last_emission_ts: int
    last_reward: int

    def as_dict(self) -> Dict[str, Any]:
        return {
            "emission_pool_total": self.emission_pool_total,
            "remaining_pool": self.remaining_pool,
            "minted_total": self.minted_total,
            "epoch_length_sec": self.epoch_length_sec,
            "genesis_ts": self.genesis_ts,
            "last_emission_ts": self.last_emission_ts,
            "last_reward": self.last_reward,
        }


class TokenomicsChainDB(aichain.ChainDB):
    def __init__(self, path: str):
        super().__init__(path)
        self.token_state_path = os.path.join(self.path, "token_state.json")
        self.token_state = self._load_token_state()

    def _load_token_state(self) -> TokenState:
        if os.path.exists(self.token_state_path):
            with open(self.token_state_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            return TokenState(
                emission_pool_total=int(raw.get("emission_pool_total", EMISSION_POOL_TOTAL)),
                remaining_pool=int(raw.get("remaining_pool", EMISSION_POOL_TOTAL)),
                minted_total=int(raw.get("minted_total", 0)),
                epoch_length_sec=int(raw.get("epoch_length_sec", EPOCH_LENGTH_SEC)),
                genesis_ts=int(raw.get("genesis_ts", self.tip().header.timestamp)),
                last_emission_ts=int(raw.get("last_emission_ts", self.tip().header.timestamp)),
                last_reward=int(raw.get("last_reward", 0)),
            )

        ts = self.tip().header.timestamp
        st = TokenState(
            emission_pool_total=EMISSION_POOL_TOTAL,
            remaining_pool=EMISSION_POOL_TOTAL,
            minted_total=0,
            epoch_length_sec=EPOCH_LENGTH_SEC,
            genesis_ts=ts,
            last_emission_ts=ts,
            last_reward=0,
        )
        self._persist_token_state(st)
        return st

    def _persist_token_state(self, st: TokenState | None = None) -> None:
        state = st or self.token_state
        with open(self.token_state_path, "w", encoding="utf-8") as f:
            json.dump(state.as_dict(), f, indent=2, sort_keys=True)

    def _state_metrics(self) -> Dict[str, float]:
        tx_count = float(len(self.mempool))
        return {
            "activity": min(2.0, 0.5 + tx_count / 20.0),
            "stability": 1.0,
            "demand": min(2.0, 0.5 + tx_count / 40.0),
        }

    def _epochs_remaining(self, timestamp: int) -> int:
        elapsed = max(0, timestamp - self.token_state.genesis_ts)
        elapsed_epochs = elapsed // self.token_state.epoch_length_sec
        # 10-year emission horizon in daily epochs
        total_epochs = 3650
        return max(1, total_epochs - int(elapsed_epochs))

    def build_block_template(self, miner_addr: str) -> aichain.Block:
        blk = super().build_block_template(miner_addr)
        if self.token_state.remaining_pool <= 0:
            return blk

        reward = tokenomics_v1.compute_block_reward(
            state_metrics=self._state_metrics(),
            remaining_pool=self.token_state.remaining_pool,
            epochs_remaining=self._epochs_remaining(blk.header.timestamp),
        )
        if reward <= 0:
            return blk

        emission_tx = aichain.Transaction(
            version=1,
            vin=[aichain.TxIn(from_addr="COINBASE")],
            vout=[aichain.TxOut(to_addr=miner_addr, amount=reward)],
            fee=0,
            nonce=0,
            memo="emission_v1",
        )
        all_txs = list(blk.txs) + [emission_tx]
        txids = [t.txid() for t in all_txs]
        hdr = aichain.BlockHeader(
            version=blk.header.version,
            prev_hash=blk.header.prev_hash,
            merkle_root=aichain.merkle_root(txids),
            timestamp=blk.header.timestamp,
            height=blk.header.height,
            bits=blk.header.bits,
            nonce=0,
        )
        return aichain.Block(header=hdr, txs=all_txs)

    def submit_block(self, blk: aichain.Block):
        ok, why = super().submit_block(blk)
        if not ok:
            return ok, why

        reward = 0
        for tx in blk.txs[1:]:
            if tx.memo == "emission_v1":
                reward += sum(o.amount for o in tx.vout)

        if reward > 0:
            reward = min(reward, self.token_state.remaining_pool)
            self.token_state.minted_total += reward
            self.token_state.remaining_pool -= reward
            self.token_state.last_reward = reward
            self.token_state.last_emission_ts = blk.header.timestamp
            self._persist_token_state()
        return ok, why


def cmd_mine(args):
    db = TokenomicsChainDB(args.datadir)
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
    print("token_emission_paid", db.token_state.last_reward)
    print("remaining_pool", db.token_state.remaining_pool)


def cmd_status(args):
    db = TokenomicsChainDB(args.datadir)
    print(json.dumps(db.token_state.as_dict(), indent=2, sort_keys=True))


def main():
    p = argparse.ArgumentParser(prog="ramia_core_v1")
    p.add_argument("--datadir", default="./aichain_data")
    sp = p.add_subparsers(dest="cmd", required=True)

    s0 = sp.add_parser("init")
    s0.set_defaults(func=lambda a: print("ok"))

    s1 = sp.add_parser("mine")
    s1.add_argument("miner_addr")
    s1.set_defaults(func=cmd_mine)

    s2 = sp.add_parser("status")
    s2.set_defaults(func=cmd_status)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
