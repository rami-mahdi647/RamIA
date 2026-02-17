#!/usr/bin/env python3
# AIChain AI-Fleet Stateful
# - No edits to aichain.py / aiguardian.py
# - AI bots + committee decisions + reproduction
# - Adds persistence (fleet_state.json) + real burst_score (per sender) + stats top bots
#
# Usage:
#   python3 aichain_aifleet_stateful.py --guardian-model guardian_model.json init
#   python3 aichain_aifleet_stateful.py --guardian-model guardian_model.json send genesis alice 100000 --fee 1000
#   python3 aichain_aifleet_stateful.py --guardian-model guardian_model.json mine x
#   python3 aichain_aifleet_stateful.py --guardian-model guardian_model.json stats --top 20
#
# Notes:
# - Fleet is huge by default; persistence keeps it stable across runs.
# - Still a prototype; this is the “lab” for your concept.

import argparse
import dataclasses
import json
import os
import random
import time
from typing import Any, Dict, List, Optional, Tuple

import aichain
import aiguardian


# ----------------------------
# Burst tracking (real burst_score)
# ----------------------------

class BurstTracker:
    """
    Tracks timestamps per sender and computes burst_score in [0..1+] roughly:
    - burst_score ~ events_in_window / max_events
    """
    def __init__(self, window_sec: int = 60, max_events: int = 10):
        self.window = int(window_sec)
        self.max_events = int(max_events)
        self.events: Dict[str, List[int]] = {}

    def observe(self, sender: str, ts: int) -> float:
        if not sender:
            return 0.0
        lst = self.events.get(sender, [])
        cutoff = ts - self.window
        lst = [t for t in lst if t >= cutoff]
        lst.append(ts)
        self.events[sender] = lst
        return float(len(lst)) / float(max(1, self.max_events))

    def snapshot(self) -> Dict[str, Any]:
        return {"window": self.window, "max_events": self.max_events, "events": self.events}

    @staticmethod
    def load(obj: Dict[str, Any]) -> "BurstTracker":
        bt = BurstTracker(window_sec=int(obj.get("window", 60)), max_events=int(obj.get("max_events", 10)))
        bt.events = {k: [int(x) for x in v] for k, v in obj.get("events", {}).items()}
        return bt


# ----------------------------
# Bot genome / bot
# ----------------------------

@dataclasses.dataclass
class BotGenome:
    w_fee: float
    w_amount: float
    w_outputs: float
    w_entropy: float
    w_memo: float
    w_burst: float
    bias: float

    def mutate(self, sigma: float = 0.05) -> "BotGenome":
        def m(x): return x + random.gauss(0.0, sigma)
        return BotGenome(
            w_fee=m(self.w_fee),
            w_amount=m(self.w_amount),
            w_outputs=m(self.w_outputs),
            w_entropy=m(self.w_entropy),
            w_memo=m(self.w_memo),
            w_burst=m(self.w_burst),
            bias=m(self.bias),
        )

    @staticmethod
    def random_init() -> "BotGenome":
        return BotGenome(
            w_fee=random.uniform(-0.5, 0.5),
            w_amount=random.uniform(-0.5, 0.5),
            w_outputs=random.uniform(-0.5, 0.5),
            w_entropy=random.uniform(-0.5, 0.5),
            w_memo=random.uniform(-0.5, 0.5),
            w_burst=random.uniform(-0.5, 0.5),
            bias=random.uniform(-0.2, 0.2),
        )

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "BotGenome":
        return BotGenome(**{k: float(v) for k, v in d.items()})


@dataclasses.dataclass
class AIBot:
    bot_id: int
    name: str
    role: str
    genome: BotGenome

    age: int = 0
    accepted: int = 0
    rejected: int = 0
    quarantined: int = 0
    mined_blocks: int = 0
    earned_fees: int = 0
    earned_subsidy: int = 0
    score: float = 0.0

    def policy_min_fee(self, feats: "aiguardian.TxFeatures") -> int:
        # normalize-ish
        x_fee = float(feats.fee) / 1e5
        x_amount = float(feats.amount) / 1e8
        x_outputs = float(feats.outputs) / 10.0
        x_entropy = float(feats.addr_entropy) / 5.0
        x_memo = float(feats.memo_len) / 200.0
        x_burst = float(feats.burst_score)  # already normalized

        z = (
            self.genome.w_fee * x_fee
            + self.genome.w_amount * x_amount
            + self.genome.w_outputs * x_outputs
            + self.genome.w_entropy * x_entropy
            + self.genome.w_memo * x_memo
            + self.genome.w_burst * x_burst
            + self.genome.bias
        )
        mult = 1.0 + max(0.0, z)
        base = 1000
        return int(base * mult)

    def decide(self, guardian_score: float, threshold: float, min_fee_required: int, offered_fee: int) -> Tuple[str, str]:
        if offered_fee < min_fee_required:
            return ("deny", "fee_too_low_for_policy")
        if guardian_score >= threshold:
            # allow quarantine for “compliance roles”
            if self.role in ("Sentinel", "Auditor"):
                return ("quarantine", "guardian_high_risk")
            return ("deny", "guardian_high_risk")
        return ("allow", "ok")

    def to_dict(self) -> Dict[str, Any]:
        d = dataclasses.asdict(self)
        d["genome"] = self.genome.to_dict()
        return d

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "AIBot":
        g = BotGenome.from_dict(d["genome"])
        dd = dict(d)
        dd["genome"] = g
        return AIBot(**dd)


# ----------------------------
# Fleet with persistence
# ----------------------------

class AIFleet:
    def __init__(
        self,
        size: int,
        seed: int,
        committee_size: int,
        reproduction_interval_blocks: int,
        elite_fraction: float,
        mutation_sigma: float,
        state_path: str,
    ):
        self.size = int(size)
        self.seed = int(seed)
        self.committee_size = int(committee_size)
        self.reproduction_interval_blocks = int(reproduction_interval_blocks)
        self.elite_fraction = float(elite_fraction)
        self.mutation_sigma = float(mutation_sigma)
        self.state_path = state_path

        self.bots: List[AIBot] = []
        self.round: int = 0

        random.seed(self.seed)

        if os.path.exists(self.state_path):
            self.load()
        else:
            self._make_fleet()
            self.save()

    def _make_fleet(self):
        roles = ["Sentinel", "Auditor", "Miner", "Dispatcher"]
        self.bots = []
        for i in range(self.size):
            role = roles[i % len(roles)]
            name = f"{role}-{i:05d}"
            self.bots.append(AIBot(
                bot_id=i,
                name=name,
                role=role,
                genome=BotGenome.random_init(),
            ))
        self.round = 0

    def save(self):
        tmp = self.state_path + ".tmp"
        obj = {
            "version": 1,
            "seed": self.seed,
            "size": self.size,
            "committee_size": self.committee_size,
            "reproduction_interval_blocks": self.reproduction_interval_blocks,
            "elite_fraction": self.elite_fraction,
            "mutation_sigma": self.mutation_sigma,
            "round": self.round,
            "bots": [b.to_dict() for b in self.bots],
        }
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False))
        os.replace(tmp, self.state_path)

    def load(self):
        with open(self.state_path, "r", encoding="utf-8") as f:
            obj = json.loads(f.read())
        self.seed = int(obj.get("seed", self.seed))
        self.size = int(obj.get("size", self.size))
        self.committee_size = int(obj.get("committee_size", self.committee_size))
        self.reproduction_interval_blocks = int(obj.get("reproduction_interval_blocks", self.reproduction_interval_blocks))
        self.elite_fraction = float(obj.get("elite_fraction", self.elite_fraction))
        self.mutation_sigma = float(obj.get("mutation_sigma", self.mutation_sigma))
        self.round = int(obj.get("round", 0))
        self.bots = [AIBot.from_dict(b) for b in obj.get("bots", [])]
        if len(self.bots) != self.size:
            # mismatch => rebuild safely
            self._make_fleet()

    def committee(self) -> List[AIBot]:
        return random.sample(self.bots, k=min(self.committee_size, len(self.bots)))

    def miner_of_round(self) -> AIBot:
        # choose best from a committee (cheap)
        c = self.committee()
        return max(c, key=lambda b: b.score)

    def update_reputation(self, bot: AIBot):
        reward = (bot.earned_fees / 1e6) + (bot.earned_subsidy / 1e7)
        penalty = (bot.rejected * 0.01) + (bot.quarantined * 0.005)
        bot.score = max(0.0, reward - penalty)

    def evolve_if_needed(self, height: int):
        if height <= 0:
            return
        if height % self.reproduction_interval_blocks != 0:
            return

        for b in self.bots:
            self.update_reputation(b)

        elites_n = max(1, int(self.elite_fraction * len(self.bots)))
        elites = sorted(self.bots, key=lambda b: b.score, reverse=True)[:elites_n]
        replace_n = elites_n
        worst = sorted(self.bots, key=lambda b: b.score)[:replace_n]

        for w in worst:
            parent = random.choice(elites)
            w.genome = parent.genome.mutate(sigma=self.mutation_sigma)
            w.role = parent.role
            w.name = f"{w.role}-{w.bot_id:05d}"
            w.age = 0
            w.accepted = w.rejected = w.quarantined = 0
            w.mined_blocks = 0
            w.earned_fees = w.earned_subsidy = 0
            w.score = 0.0

        self.round += 1


# ----------------------------
# Bridge patching ChainDB
# ----------------------------

def _tx_sender(tx: "aichain.Transaction") -> str:
    if not tx.vin:
        return ""
    return tx.vin[0].from_addr or ""


def _tx_to_guardian_dict(tx: "aichain.Transaction", burst_score: float) -> Dict[str, Any]:
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
        "burst_score": float(burst_score),
        "timestamp": int(aichain.now_ts()),
    }


def install_stateful_patch(
    model_path: str,
    threshold: float,
    fleet: AIFleet,
    burst: BurstTracker,
    log_path: Optional[str] = None,
) -> Tuple[bool, str]:
    model = aiguardian.LogisticModel.load(model_path)
    guardian = aiguardian.Guardian(model, threshold=threshold)

    original_add = aichain.ChainDB.add_tx_to_mempool
    original_build_tpl = aichain.ChainDB.build_block_template
    original_submit = aichain.ChainDB.submit_block

    def _log(obj: Dict[str, Any]):
        if not log_path:
            return
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(obj, sort_keys=True, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def guarded_add(self: "aichain.ChainDB", tx: "aichain.Transaction"):
        if not hasattr(self, "quarantine"):
            self.quarantine = {}  # type: ignore[attr-defined]

        if len(tx.vin) == 1 and tx.vin[0].from_addr == "COINBASE":
            return original_add(self, tx)

        ts = int(aichain.now_ts())
        sender = _tx_sender(tx)
        bscore = burst.observe(sender, ts)

        txd = _tx_to_guardian_dict(tx, burst_score=bscore)
        feats = aiguardian.extract_features(txd)
        gscore = guardian.score(txd)

        committee = fleet.committee()
        votes = {"allow": 0, "deny": 0, "quarantine": 0}
        reasons: Dict[str, int] = {}
        min_fee_suggestions: List[int] = []

        for bot in committee:
            min_fee = bot.policy_min_fee(feats)
            min_fee_suggestions.append(min_fee)
            decision, reason = bot.decide(gscore, threshold, min_fee, int(tx.fee))
            votes[decision] += 1
            reasons[reason] = reasons.get(reason, 0) + 1

        decision = max(votes.items(), key=lambda kv: kv[1])[0]
        top_reason = max(reasons.items(), key=lambda kv: kv[1])[0] if reasons else "ok"
        leader = max(committee, key=lambda b: b.score)

        # Use median as “recommended min fee” from the committee policy
        min_fee_suggestions.sort()
        recommended_fee = min_fee_suggestions[len(min_fee_suggestions) // 2] if min_fee_suggestions else 1000

        if decision == "allow":
            ok, out = original_add(self, tx)
            if ok:
                leader.accepted += 1
            else:
                leader.rejected += 1

            _log({
                "ts": ts,
                "action": "mempool_admission",
                "txid": tx.txid(),
                "sender": sender,
                "guardian_score": float(gscore),
                "threshold": float(threshold),
                "burst_score": float(bscore),
                "decision": "allow" if ok else "deny",
                "reason": top_reason if ok else out,
                "leader": leader.name,
                "votes": votes,
                "recommended_fee": int(recommended_fee),
            })

            # persist bot/burst state occasionally
            fleet.save()
            return (ok, out)

        warning = {
            "allow": False,
            "warning": True,
            "txid": tx.txid(),
            "sender": sender,
            "message": "Decisión del comité IA",
            "decision": decision,
            "leader": leader.name,
            "votes": votes,
            "guardian_score": float(gscore),
            "threshold": float(threshold),
            "burst_score": float(bscore),
            "reason": top_reason,
            "recommended_fee": int(recommended_fee),
            "how_to_reduce_penalty": [
                "Reduce ráfagas: espera entre transacciones (burst_score alto sube el coste).",
                "Sube el fee hacia recommended_fee para mejorar aceptación.",
                "Evita memos largos y demasiados outputs.",
            ],
        }

        if decision == "quarantine":
            self.quarantine[tx.txid()] = tx.to_dict()  # type: ignore[attr-defined]
            leader.quarantined += 1
            _log({"ts": ts, "action": "quarantine", **warning})
            fleet.save()
            return (False, json.dumps(warning, ensure_ascii=False))

        leader.rejected += 1
        _log({"ts": ts, "action": "deny", **warning})
        fleet.save()
        return (False, json.dumps(warning, ensure_ascii=False))

    def fleet_build_template(self: "aichain.ChainDB", miner_addr: str):
        miner = fleet.miner_of_round()
        return original_build_tpl(self, miner.name)

    def wrapped_submit(self: "aichain.ChainDB", blk: "aichain.Block"):
        ok, why = original_submit(self, blk)
        if ok:
            miner_addr = blk.txs[0].vout[0].to_addr if blk.txs and blk.txs[0].vout else ""
            paid = sum(o.amount for o in blk.txs[0].vout)
            fees = sum(t.fee for t in blk.txs[1:])
            subsidy = max(0, paid - fees)

            bot = None
            if "-" in miner_addr:
                try:
                    bid = int(miner_addr.split("-")[-1])
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

            fleet.evolve_if_needed(self.height())
            fleet.save()
        return (ok, why)

    aichain.ChainDB.add_tx_to_mempool = guarded_add  # type: ignore[attr-defined]
    aichain.ChainDB.build_block_template = fleet_build_template  # type: ignore[attr-defined]
    aichain.ChainDB.submit_block = wrapped_submit  # type: ignore[attr-defined]

    return True, "stateful ai-fleet patch installed"


# ----------------------------
# CLI commands
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
    if ok:
        print("txid", out)
        return
    try:
        print(json.dumps(json.loads(out), indent=2, ensure_ascii=False))
    except Exception:
        print("error", out)

def cmd_mine(args):
    db = aichain.ChainDB(args.datadir)
    tpl = db.build_block_template(args.any_miner_addr)  # ignored
    mined = db._mine_block(tpl)
    ok, why = db.submit_block(mined)
    if not ok:
        print("error", why)
        return
    print("ok accepted")
    print("height", db.height())
    print("hash", mined.block_hash())
    print("coinbase_to", mined.txs[0].vout[0].to_addr if mined.txs[0].vout else "")
    print("coinbase_paid", sum(o.amount for o in mined.txs[0].vout))

def cmd_stats(args, fleet: AIFleet):
    # show top bots by score
    bots = sorted(fleet.bots, key=lambda b: b.score, reverse=True)[: args.top]
    rows = []
    for b in bots:
        rows.append({
            "name": b.name,
            "role": b.role,
            "score": round(b.score, 6),
            "mined": b.mined_blocks,
            "accepted": b.accepted,
            "rejected": b.rejected,
            "quarantined": b.quarantined,
            "fees": b.earned_fees,
            "subsidy": b.earned_subsidy,
            "age": b.age,
        })
    print(json.dumps({
        "fleet_round": fleet.round,
        "fleet_size": fleet.size,
        "top": rows
    }, indent=2, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser(prog="aichain_aifleet_stateful")
    p.add_argument("--datadir", default="./aichain_data")
    p.add_argument("--guardian-model", required=True)
    p.add_argument("--threshold", type=float, default=0.7)

    p.add_argument("--fleet-size", type=int, default=100000)
    p.add_argument("--committee-size", type=int, default=21)
    p.add_argument("--seed", type=int, default=1337)

    p.add_argument("--evolve-every", type=int, default=50)
    p.add_argument("--elite-frac", type=float, default=0.05)
    p.add_argument("--mut-sigma", type=float, default=0.05)

    p.add_argument("--fleet-state", default="./fleet_state.json")
    p.add_argument("--burst-state", default="./burst_state.json")
    p.add_argument("--burst-window", type=int, default=60)
    p.add_argument("--burst-max", type=int, default=10)

    p.add_argument("--log", default="", help="Optional JSONL log")

    sp = p.add_subparsers(dest="cmd", required=True)

    sp0 = sp.add_parser("init")
    sp0.set_defaults(func=lambda a: cmd_init(a))

    sp1 = sp.add_parser("send")
    sp1.add_argument("from_addr")
    sp1.add_argument("to_addr")
    sp1.add_argument("amount", type=int)
    sp1.add_argument("--fee", type=int, default=1000)
    sp1.add_argument("--memo", default="")
    sp1.set_defaults(func=lambda a: cmd_send(a))

    sp2 = sp.add_parser("mine")
    sp2.add_argument("any_miner_addr", help="ignored; fleet selects miner bot")
    sp2.set_defaults(func=lambda a: cmd_mine(a))

    sp3 = sp.add_parser("stats")
    sp3.add_argument("--top", type=int, default=20)
    # func set after fleet init

    args = p.parse_args()

    # load/create fleet
    fleet = AIFleet(
        size=args.fleet_size,
        seed=args.seed,
        committee_size=args.committee_size,
        reproduction_interval_blocks=args.evolve_every,
        elite_fraction=args.elite_frac,
        mutation_sigma=args.mut_sigma,
        state_path=args.fleet_state,
    )

    # load/create burst tracker
    if os.path.exists(args.burst_state):
        with open(args.burst_state, "r", encoding="utf-8") as f:
            burst = BurstTracker.load(json.loads(f.read()))
    else:
        burst = BurstTracker(window_sec=args.burst_window, max_events=args.burst_max)
        with open(args.burst_state, "w", encoding="utf-8") as f:
            f.write(json.dumps(burst.snapshot(), ensure_ascii=False))

    ok, msg = install_stateful_patch(
        model_path=args.guardian_model,
        threshold=args.threshold,
        fleet=fleet,
        burst=burst,
        log_path=(args.log or None),
    )
    if not ok:
        raise SystemExit(msg)

    # if stats, run stats without needing ChainDB
    if args.cmd == "stats":
        cmd_stats(args, fleet)
        return

    # run command
    args.func(args)

    # persist burst state at end of run
    try:
        with open(args.burst_state, "w", encoding="utf-8") as f:
            f.write(json.dumps(burst.snapshot(), ensure_ascii=False))
    except Exception:
        pass


if __name__ == "__main__":
    main()
