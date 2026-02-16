#!/usr/bin/env python3
# AIChain AI-Fleet: 100k AI nodes concept (simulated)
# - Does NOT modify aichain.py or aiguardian.py
# - Creates "AI nodes" with names/roles, scoring, and reproduction (mutation).
# - Patches mempool admission + mining selection to be driven by the bots.
#
# This is a research prototype / playground.

import argparse
import dataclasses
import json
import math
import os
import random
import time
from typing import Any, Dict, List, Optional, Tuple

import aichain
import aiguardian


# ----------------------------
# Bot identity + brain
# ----------------------------

@dataclasses.dataclass
class BotGenome:
    # Small param vector; treat as a "tiny neural net" seed.
    # You can replace with real NN weights later.
    w_fee: float
    w_amount: float
    w_outputs: float
    w_entropy: float
    w_memo: float
    bias: float

    def mutate(self, sigma: float = 0.05) -> "BotGenome":
        def m(x): return x + random.gauss(0.0, sigma)
        return BotGenome(
            w_fee=m(self.w_fee),
            w_amount=m(self.w_amount),
            w_outputs=m(self.w_outputs),
            w_entropy=m(self.w_entropy),
            w_memo=m(self.w_memo),
            bias=m(self.bias),
        )

    @staticmethod
    def random_init() -> "BotGenome":
        # small random init
        return BotGenome(
            w_fee=random.uniform(-0.5, 0.5),
            w_amount=random.uniform(-0.5, 0.5),
            w_outputs=random.uniform(-0.5, 0.5),
            w_entropy=random.uniform(-0.5, 0.5),
            w_memo=random.uniform(-0.5, 0.5),
            bias=random.uniform(-0.2, 0.2),
        )


@dataclasses.dataclass
class AIBot:
    bot_id: int
    name: str
    role: str  # e.g., "Sentinel", "Auditor", "Miner", "Dispatcher"
    genome: BotGenome

    # Lifetime stats
    age: int = 0
    accepted: int = 0
    rejected: int = 0
    quarantined: int = 0
    mined_blocks: int = 0
    earned_fees: int = 0
    earned_subsidy: int = 0

    # “Trust” / reputation
    score: float = 0.0

    def policy_min_fee(self, tx_features: "aiguardian.TxFeatures") -> int:
        """
        Bot-specific fee policy:
        outputs/memo/entropy increase fee requirement; higher fee lowers suspicion.
        """
        # normalize-ish
        x_fee = float(tx_features.fee) / 1e5
        x_amount = float(tx_features.amount) / 1e8
        x_outputs = float(tx_features.outputs) / 10.0
        x_entropy = float(tx_features.addr_entropy) / 5.0
        x_memo = float(tx_features.memo_len) / 200.0

        z = (
            self.genome.w_fee * x_fee
            + self.genome.w_amount * x_amount
            + self.genome.w_outputs * x_outputs
            + self.genome.w_entropy * x_entropy
            + self.genome.w_memo * x_memo
            + self.genome.bias
        )
        # map z -> multiplier
        mult = 1.0 + max(0.0, z)  # only penalize upward
        base = 1000
        return int(base * mult)

    def decide(self, guardian_score: float, threshold: float, min_fee_required: int, offered_fee: int) -> Tuple[str, str]:
        """
        Returns (decision, reason):
          decision in {"allow","deny","quarantine"}
        """
        if offered_fee < min_fee_required:
            return ("deny", "fee_too_low_for_policy")
        if guardian_score >= threshold:
            # bots can choose quarantine instead of deny
            if self.role in ("Sentinel", "Auditor"):
                return ("quarantine", "guardian_high_risk")
            return ("deny", "guardian_high_risk")
        return ("allow", "ok")


# ----------------------------
# Fleet manager (100k bots concept)
# ----------------------------

class AIFleet:
    """
    Manages many bots efficiently:
    - We can *simulate* 100k bots without using them all each decision.
    - Choose a small committee per tx/block (committee_size).
    """

    def __init__(
        self,
        size: int,
        seed: int = 1337,
        committee_size: int = 21,
        reproduction_interval_blocks: int = 50,
        elite_fraction: float = 0.05,
        mutation_sigma: float = 0.05,
    ):
        random.seed(seed)
        self.size = size
        self.committee_size = committee_size
        self.reproduction_interval_blocks = reproduction_interval_blocks
        self.elite_fraction = elite_fraction
        self.mutation_sigma = mutation_sigma

        self.bots: List[AIBot] = []
        self._make_fleet()

    def _make_fleet(self):
        roles = ["Sentinel", "Auditor", "Miner", "Dispatcher"]
        for i in range(self.size):
            role = roles[i % len(roles)]
            name = f"{role}-{i:05d}"
            self.bots.append(AIBot(
                bot_id=i,
                name=name,
                role=role,
                genome=BotGenome.random_init(),
            ))

    def committee(self) -> List[AIBot]:
        # sample committee without scanning entire fleet
        return random.sample(self.bots, k=min(self.committee_size, len(self.bots)))

    def miner_of_round(self) -> AIBot:
        # weighted by reputation score (softmax-ish)
        # avoid heavy math; sample a committee and pick best
        c = self.committee()
        return max(c, key=lambda b: b.score)

    def update_reputation(self, bot: AIBot):
        # simple reward shaping: fees+subsidy - penalties
        reward = (bot.earned_fees / 1e6) + (bot.earned_subsidy / 1e7)
        penalty = (bot.rejected * 0.01) + (bot.quarantined * 0.005)
        bot.score = max(0.0, reward - penalty)

    def evolve_if_needed(self, height: int):
        if height == 0:
            return
        if height % self.reproduction_interval_blocks != 0:
            return

        # Update reputations
        for b in self.bots:
            self.update_reputation(b)

        # Select elites
        elites_n = max(1, int(self.elite_fraction * len(self.bots)))
        elites = sorted(self.bots, key=lambda b: b.score, reverse=True)[:elites_n]

        # Replace worst fraction with mutated children of elites
        replace_n = elites_n
        worst = sorted(self.bots, key=lambda b: b.score)[:replace_n]

        for w in worst:
            parent = random.choice(elites)
            child_genome = parent.genome.mutate(sigma=self.mutation_sigma)
            w.genome = child_genome
            w.role = parent.role  # inherit role for now
            w.name = f"{w.role}-{w.bot_id:05d}"
            w.age = 0
            w.accepted = w.rejected = w.quarantined = 0
            w.mined_blocks = 0
            w.earned_fees = w.earned_subsidy = 0
            w.score = 0.0


# ----------------------------
# Bridge: patch ChainDB to use Fleet + Guardian
# ----------------------------

def _tx_to_guardian_dict(tx: "aichain.Transaction") -> Dict[str, Any]:
    amount = float(sum(o.amount for o in tx.vout))
    fee = float(tx.fee)
    outputs = int(len(tx.vout))
    memo = str(tx.memo or "")
    to_addr = tx.vout[0].to_addr if tx.vout else ""
    return {
        "amount": amount,
        "fee": fee,
        "outputs": outputs,
        "memo": memo,
        "to_addr": to_addr,
        "burst_score": 0.0,
        "timestamp": int(aichain.now_ts()),
    }


def install_ai_fleet_patch(
    model_path: str,
    threshold: float,
    fleet: AIFleet,
    log_path: Optional[str] = None,
) -> Tuple[bool, str]:
    model = aiguardian.LogisticModel.load(model_path)
    guardian = aiguardian.Guardian(model, threshold=threshold)

    original_add = aichain.ChainDB.add_tx_to_mempool
    original_build_tpl = aichain.ChainDB.build_block_template

    def _log(obj: Dict[str, Any]):
        if not log_path:
            return
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(obj, sort_keys=True) + "\n")
        except Exception:
            pass

    def guarded_add(self: "aichain.ChainDB", tx: "aichain.Transaction"):
        # init quarantine store on db instance
        if not hasattr(self, "quarantine"):
            self.quarantine = {}  # type: ignore[attr-defined]

        # pass-through coinbase (shouldn't happen)
        if len(tx.vin) == 1 and tx.vin[0].from_addr == "COINBASE":
            return original_add(self, tx)

        txd = _tx_to_guardian_dict(tx)
        feats = aiguardian.extract_features(txd)
        gscore = guardian.score(txd)

        # committee vote
        committee = fleet.committee()
        votes = {"allow": 0, "deny": 0, "quarantine": 0}
        reasons: Dict[str, int] = {}

        for bot in committee:
            min_fee = bot.policy_min_fee(feats)
            decision, reason = bot.decide(gscore, threshold, min_fee, int(tx.fee))
            votes[decision] += 1
            reasons[reason] = reasons.get(reason, 0) + 1

        # majority decision
        decision = max(votes.items(), key=lambda kv: kv[1])[0]
        top_reason = max(reasons.items(), key=lambda kv: kv[1])[0] if reasons else "ok"

        # pick a "responsible bot" to attribute this action (leader = best score in committee)
        leader = max(committee, key=lambda b: b.score)

        if decision == "allow":
            ok, out = original_add(self, tx)
            if ok:
                leader.accepted += 1
            else:
                leader.rejected += 1

            _log({
                "ts": int(aichain.now_ts()),
                "action": "mempool_admission",
                "txid": tx.txid(),
                "guardian_score": float(gscore),
                "threshold": float(threshold),
                "decision": "allow" if ok else "deny",
                "reason": top_reason if ok else out,
                "leader": leader.name,
                "votes": votes,
            })
            return (ok, out)

        if decision == "quarantine":
            qid = tx.txid()
            self.quarantine[qid] = tx.to_dict()  # type: ignore[attr-defined]
            leader.quarantined += 1
            payload = {
                "allow": False,
                "warning": True,
                "message": "Transacción enviada a cuarentena por comité IA",
                "txid": qid,
                "guardian_score": float(gscore),
                "threshold": float(threshold),
                "leader": leader.name,
                "votes": votes,
                "reason": top_reason,
                "hint": "Sube fee, reduce outputs/memo, evita ráfagas. Reintenta.",
            }
            _log({"ts": int(aichain.now_ts()), "action": "quarantine", **payload})
            return (False, json.dumps(payload, ensure_ascii=False))

        # deny
        leader.rejected += 1
        payload = {
            "allow": False,
            "warning": True,
            "message": "Transacción rechazada por comité IA",
            "txid": tx.txid(),
            "guardian_score": float(gscore),
            "threshold": float(threshold),
            "leader": leader.name,
            "votes": votes,
            "reason": top_reason,
        }
        _log({"ts": int(aichain.now_ts()), "action": "deny", **payload})
        return (False, json.dumps(payload, ensure_ascii=False))

    def fleet_build_template(self: "aichain.ChainDB", miner_addr: str):
        """
        Override miner selection:
        - ignore provided miner_addr and choose AI miner of the round
        - pay coinbase to the chosen bot name (acts as address)
        """
        miner = fleet.miner_of_round()
        # coinbase "address" = miner.name (string)
        return original_build_tpl(self, miner.name)

    def fleet_submit_block_hook(self: "aichain.ChainDB", blk: "aichain.Block"):
        # After a block is accepted, pay rewards attribution to the miner bot
        # by reading coinbase output address.
        miner_addr = blk.txs[0].vout[0].to_addr if blk.txs and blk.txs[0].vout else ""
        paid = sum(o.amount for o in blk.txs[0].vout)

        # split into subsidy vs fees roughly (we can estimate fees as sum of tx fees)
        fees = sum(t.fee for t in blk.txs[1:])
        subsidy = max(0, paid - fees)

        # find miner bot
        # (fast path: parse bot_id from name suffix; else linear scan fallback)
        bot = None
        if "-" in miner_addr:
            try:
                suffix = miner_addr.split("-")[-1]
                bid = int(suffix)
                if 0 <= bid < len(fleet.bots):
                    bot = fleet.bots[bid]
            except Exception:
                bot = None
        if bot is None:
            for b in fleet.bots:
                if b.name == miner_addr:
                    bot = b
                    break

        if bot:
            bot.mined_blocks += 1
            bot.earned_fees += int(fees)
            bot.earned_subsidy += int(subsidy)
            bot.age += 1
            fleet.update_reputation(bot)

        # evolve occasionally
        fleet.evolve_if_needed(self.height())

    # install patches
    aichain.ChainDB.add_tx_to_mempool = guarded_add  # type: ignore[attr-defined]
    aichain.ChainDB.build_block_template = fleet_build_template  # type: ignore[attr-defined]

    # wrap submit_block to call hook after acceptance
    original_submit = aichain.ChainDB.submit_block
    def wrapped_submit(self: "aichain.ChainDB", blk: "aichain.Block"):
        ok, why = original_submit(self, blk)
        if ok:
            fleet_submit_block_hook(self, blk)
        return (ok, why)
    aichain.ChainDB.submit_block = wrapped_submit  # type: ignore[attr-defined]

    return True, "ai-fleet patch installed"


# ----------------------------
# CLI
# ----------------------------

def cmd_init(args):
    db = aichain.ChainDB(args.datadir)
    print("ok")
    print("height", db.height())
    print("tip", db.tip().block_hash())

def cmd_send(args):
    db = aichain.ChainDB(args.datadir)
    tx = db.make_tx(args.from_addr, args.to_addr, args.amount, args.fee, memo=args.memo)
    ok, out = db.add_tx_to_mempool(tx)
    if not ok:
        try:
            print(json.dumps(json.loads(out), indent=2, ensure_ascii=False))
        except Exception:
            print("error", out)
        return
    print("txid", out)

def cmd_mine(args):
    db = aichain.ChainDB(args.datadir)
    # miner address ignored; fleet selects miner
    tpl = db.build_block_template(args.any_miner_addr)
    mined = db._mine_block(tpl)
    ok, why = db.submit_block(mined)
    if not ok:
        print("error", why)
        return
    print("ok accepted")
    print("height", db.height())
    print("hash", mined.block_hash())
    print("coinbase_paid", sum(o.amount for o in mined.txs[0].vout))
    print("coinbase_to", mined.txs[0].vout[0].to_addr if mined.txs[0].vout else "")

def cmd_stats(args):
    # show top bots (light)
    # Note: stats are in-memory during this run; for persistence add a JSON state file.
    print("Run with --log to record decisions. For persistent fleet state, add a fleet_state.json (next step).")
    print("Tip: keep a long-running process for continuous evolution.")

def main():
    p = argparse.ArgumentParser(prog="aichain_aifleet")
    p.add_argument("--datadir", default="./aichain_data")
    p.add_argument("--guardian-model", required=True)
    p.add_argument("--threshold", type=float, default=0.7)

    p.add_argument("--fleet-size", type=int, default=100000)
    p.add_argument("--committee-size", type=int, default=21)
    p.add_argument("--seed", type=int, default=1337)

    p.add_argument("--evolve-every", type=int, default=50)
    p.add_argument("--elite-frac", type=float, default=0.05)
    p.add_argument("--mut-sigma", type=float, default=0.05)

    p.add_argument("--log", default="", help="Optional JSONL log")

    sp = p.add_subparsers(dest="cmd", required=True)

    sp0 = sp.add_parser("init")
    sp0.set_defaults(func=cmd_init)

    sp1 = sp.add_parser("send")
    sp1.add_argument("from_addr")
    sp1.add_argument("to_addr")
    sp1.add_argument("amount", type=int)
    sp1.add_argument("--fee", type=int, default=1000)
    sp1.add_argument("--memo", default="")
    sp1.set_defaults(func=cmd_send)

    sp2 = sp.add_parser("mine")
    sp2.add_argument("any_miner_addr", help="ignored; fleet selects miner bot")
    sp2.set_defaults(func=cmd_mine)

    sp3 = sp.add_parser("stats")
    sp3.set_defaults(func=cmd_stats)

    args = p.parse_args()

    fleet = AIFleet(
        size=args.fleet_size,
        seed=args.seed,
        committee_size=args.committee_size,
        reproduction_interval_blocks=args.evolve_every,
        elite_fraction=args.elite_frac,
        mutation_sigma=args.mut_sigma,
    )

    ok, msg = install_ai_fleet_patch(
        model_path=args.guardian_model,
        threshold=args.threshold,
        fleet=fleet,
        log_path=(args.log or None),
    )
    if not ok:
        raise SystemExit(msg)

    args.func(args)


if __name__ == "__main__":
    main()
