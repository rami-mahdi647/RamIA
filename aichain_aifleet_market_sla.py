#!/usr/bin/env python3
# AIChain AI-Fleet Marketplace + Spot Pricing + SLA (Prototype)
#
# Adds on top of the market concept:
# - Bot tiers (Bronze/Silver/Gold/Platinum)
# - Spot pricing (dynamic renters pool share) based on demand & congestion
# - SLA/Uptime modifiers (renters get penalized if bot uptime is low)
#
# No edits to aichain.py / aiguardian.py / aichain_aifleet_market.py
# Standalone entrypoint that patches runtime.

import argparse
import dataclasses
import hashlib
import json
import os
import random
import time
from typing import Any, Dict, List, Optional, Tuple

import aichain
import aiguardian


# ----------------------------
# Helpers
# ----------------------------

def now_ts() -> int:
    return int(time.time())

def h256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def jcanon(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")

def ensure_dir(path: str):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)


# ----------------------------
# Simple privacy receipt (same idea, kept minimal here)
# ----------------------------

def bucket_score(score: float) -> str:
    if score >= 0.90: return "very_high"
    if score >= 0.70: return "high"
    if score >= 0.50: return "med"
    return "low"

def make_receipt(txid: str, reason_code: str, score_bucket: str) -> Dict[str, Any]:
    secret = os.urandom(16).hex()
    payload = {"txid": txid, "ts": now_ts(), "reason_code": reason_code, "score_bucket": score_bucket, "secret": secret}
    commitment = h256(jcanon(payload))
    proof_stub = h256(("proof:" + commitment).encode("utf-8"))
    return {
        "txid": txid,
        "receipt_commitment": commitment,
        "receipt_proof": proof_stub,
        "note": "Privacy receipt (stub). Replace with real ZK proof later.",
        "reveal_secret": secret,      # returned only to caller if privacy-mode reveal_to_sender
        "reason_code": reason_code,   # idem
        "score_bucket": score_bucket,
    }


# ----------------------------
# Burst tracking
# ----------------------------

class BurstTracker:
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
    def load(path: str, window_sec: int, max_events: int) -> "BurstTracker":
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                obj = json.loads(f.read())
            bt = BurstTracker(int(obj.get("window", window_sec)), int(obj.get("max_events", max_events)))
            bt.events = {k: [int(x) for x in v] for k, v in obj.get("events", {}).items()}
            return bt
        return BurstTracker(window_sec, max_events)

    def save(self, path: str):
        ensure_dir(path)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(self.snapshot(), ensure_ascii=False))
        os.replace(tmp, path)


# ----------------------------
# Fleet state with tiers + SLA
# ----------------------------

TIERS = ["Bronze", "Silver", "Gold", "Platinum"]

def tier_from_score(score: float) -> str:
    # These cutoffs are arbitrary; tune later.
    if score >= 5.0: return "Platinum"
    if score >= 2.0: return "Gold"
    if score >= 0.7: return "Silver"
    return "Bronze"

@dataclasses.dataclass
class BotGenome:
    w_fee: float
    w_amount: float
    w_outputs: float
    w_entropy: float
    w_memo: float
    w_burst: float
    bias: float

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "BotGenome":
        return BotGenome(**{k: float(v) for k, v in d.items()})

    @staticmethod
    def random_init(seed: int) -> "BotGenome":
        r = random.Random(seed)
        return BotGenome(
            w_fee=r.uniform(-0.5, 0.5),
            w_amount=r.uniform(-0.5, 0.5),
            w_outputs=r.uniform(-0.5, 0.5),
            w_entropy=r.uniform(-0.5, 0.5),
            w_memo=r.uniform(-0.5, 0.5),
            w_burst=r.uniform(-0.5, 0.5),
            bias=r.uniform(-0.2, 0.2),
        )

@dataclasses.dataclass
class AIBot:
    bot_id: int
    name: str
    role: str
    genome: BotGenome

    score: float = 0.0
    tier: str = "Bronze"

    # SLA fields
    uptime_score: float = 0.98       # 0..1
    last_heartbeat_ts: int = 0

    mined_blocks: int = 0
    earned_fees: int = 0
    earned_subsidy: int = 0

    accepted: int = 0
    rejected: int = 0
    quarantined: int = 0

    def policy_min_fee(self, feats: "aiguardian.TxFeatures") -> int:
        x_fee = float(feats.fee) / 1e5
        x_amount = float(feats.amount) / 1e8
        x_outputs = float(feats.outputs) / 10.0
        x_entropy = float(feats.addr_entropy) / 5.0
        x_memo = float(feats.memo_len) / 200.0
        x_burst = float(feats.burst_score)

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
            if self.role in ("Sentinel", "Auditor"):
                return ("quarantine", "guardian_high_risk")
            return ("deny", "guardian_high_risk")
        return ("allow", "ok")

    def update_tier(self):
        self.tier = tier_from_score(self.score)

    def heartbeat(self):
        self.last_heartbeat_ts = now_ts()

    def degrade_uptime(self, amount: float):
        self.uptime_score = max(0.0, self.uptime_score - float(amount))

    def improve_uptime(self, amount: float):
        self.uptime_score = min(1.0, self.uptime_score + float(amount))

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


class FleetState:
    def __init__(self, path: str, size: int, seed: int, committee_size: int):
        self.path = path
        self.size = int(size)
        self.seed = int(seed)
        self.committee_size = int(committee_size)
        self.bots: List[AIBot] = []
        if os.path.exists(self.path):
            self.load()
        else:
            self._init()
            self.save()

    def _init(self):
        roles = ["Sentinel", "Auditor", "Miner", "Dispatcher"]
        self.bots = []
        for i in range(self.size):
            role = roles[i % len(roles)]
            name = f"{role}-{i:05d}"
            genome = BotGenome.random_init(self.seed * 1000003 + i)
            self.bots.append(AIBot(
                bot_id=i,
                name=name,
                role=role,
                genome=genome,
                score=0.0,
                tier="Bronze",
                uptime_score=0.98,
                last_heartbeat_ts=0,
            ))

    def save(self):
        ensure_dir(self.path)
        tmp = self.path + ".tmp"
        obj = {
            "version": 2,
            "size": self.size,
            "seed": self.seed,
            "committee_size": self.committee_size,
            "bots": [b.to_dict() for b in self.bots],
        }
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False))
        os.replace(tmp, self.path)

    def load(self):
        with open(self.path, "r", encoding="utf-8") as f:
            obj = json.loads(f.read())
        self.size = int(obj.get("size", self.size))
        self.seed = int(obj.get("seed", self.seed))
        self.committee_size = int(obj.get("committee_size", self.committee_size))
        self.bots = [AIBot.from_dict(b) for b in obj.get("bots", [])]
        if len(self.bots) != self.size:
            self._init()

    def committee(self) -> List[AIBot]:
        r = random.Random(self.seed + now_ts() // 10)
        k = min(self.committee_size, len(self.bots))
        return [self.bots[i] for i in r.sample(range(len(self.bots)), k=k)]

    def miner_of_round(self) -> AIBot:
        c = self.committee()
        return max(c, key=lambda b: b.score)

    def update_score(self, bot: AIBot):
        reward = (bot.earned_fees / 1e6) + (bot.earned_subsidy / 1e7)
        penalty = (bot.rejected * 0.01) + (bot.quarantined * 0.005)
        bot.score = max(0.0, reward - penalty)
        bot.update_tier()


# ----------------------------
# Rental Market with spot pricing + SLA
# ----------------------------

class RentalMarket:
    def __init__(self, path: str):
        self.path = path
        self.state: Dict[str, Any] = {
            "version": 2,
            "leases": {},
            "bot_leases": {},
            "balances": {},
            "spot": {
                "base_renters_pool_bps": 6000,   # starting point (60%)
                "min_renters_pool_bps": 2000,
                "max_renters_pool_bps": 9000,
                "last_quote": {},
            }
        }
        if os.path.exists(self.path):
            self.load()
        else:
            self.save()

    def save(self):
        ensure_dir(self.path)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(self.state, ensure_ascii=False))
        os.replace(tmp, self.path)

    def load(self):
        with open(self.path, "r", encoding="utf-8") as f:
            self.state = json.loads(f.read())

    def active_leases_count(self) -> int:
        c = 0
        for lid, lease in self.state["leases"].items():
            if int(lease.get("expires_ts", 0)) > now_ts():
                c += 1
        return c

    def bot_active_leases(self, bot_id: int) -> List[Tuple[str, Dict[str, Any]]]:
        key = str(bot_id)
        out = []
        for lid in self.state["bot_leases"].get(key, []):
            lease = self.state["leases"].get(lid)
            if not lease:
                continue
            if int(lease["expires_ts"]) <= now_ts():
                continue
            out.append((lid, lease))
        return out

    def spot_quote(self, mempool_size: int, active_leases: int, tier: str) -> Dict[str, Any]:
        """
        GPU-like spot market:
        - More demand (leases) => operator keeps more, renters share smaller.
        - More congestion (mempool) => operator keeps more (network cost).
        - Higher tier bots can be priced differently.
        """
        spot = self.state.get("spot", {})
        base = int(spot.get("base_renters_pool_bps", 6000))
        mn = int(spot.get("min_renters_pool_bps", 2000))
        mx = int(spot.get("max_renters_pool_bps", 9000))

        # Demand factor (leases): every +100 leases reduces renters pool by 100 bps
        demand_penalty = int((active_leases / 100.0) * 100)
        # Congestion factor (mempool): every +500 tx reduces renters pool by 100 bps
        cong_penalty = int((mempool_size / 500.0) * 100)

        renters_pool = base - demand_penalty - cong_penalty

        # Tier adjustments: better bots cost more -> renters pool reduced a bit
        tier_penalty = {"Bronze": 0, "Silver": 50, "Gold": 100, "Platinum": 150}.get(tier, 0)
        renters_pool -= tier_penalty

        renters_pool = max(mn, min(mx, renters_pool))

        quote = {
            "renters_pool_bps": int(renters_pool),
            "operator_pool_bps": int(10000 - renters_pool),
            "mempool_size": int(mempool_size),
            "active_leases": int(active_leases),
            "tier": tier,
            "components": {
                "base_renters_pool_bps": base,
                "demand_penalty_bps": demand_penalty,
                "congestion_penalty_bps": cong_penalty,
                "tier_penalty_bps": tier_penalty,
            }
        }
        spot["last_quote"] = quote
        self.state["spot"] = spot
        self.save()
        return quote

    def create_lease(self, renter_id: str, bot_id: int, share_bps: int, duration_sec: int) -> str:
        share_bps = int(max(0, min(10000, share_bps)))
        lease_id = h256(jcanon({"r": renter_id, "b": bot_id, "t": now_ts(), "n": os.urandom(8).hex()}))[:16]
        expires = now_ts() + int(max(60, duration_sec))
        self.state["leases"][lease_id] = {
            "renter_id": renter_id,
            "bot_id": int(bot_id),
            "share_bps": share_bps,
            "expires_ts": int(expires),
            "created_ts": now_ts(),
        }
        key = str(bot_id)
        self.state["bot_leases"].setdefault(key, []).append(lease_id)
        self.save()
        return lease_id

    def close_lease(self, lease_id: str) -> bool:
        lease = self.state["leases"].get(lease_id)
        if not lease:
            return False
        bot_id = str(lease["bot_id"])
        self.state["leases"].pop(lease_id, None)
        if bot_id in self.state["bot_leases"]:
            self.state["bot_leases"][bot_id] = [x for x in self.state["bot_leases"][bot_id] if x != lease_id]
        self.save()
        return True

    def allocate_reward(self, bot: AIBot, total_reward: int, renters_pool_bps: int) -> Dict[str, Any]:
        """
        Apply SLA: renters payout multiplied by uptime_score.
        If uptime is low, renters get penalized; operator keeps remainder.
        """
        leases = self.bot_active_leases(bot.bot_id)
        renters_pool = (int(total_reward) * int(renters_pool_bps)) // 10000
        operator_pool = int(total_reward) - renters_pool

        if renters_pool <= 0 or not leases:
            return {
                "bot_id": bot.bot_id,
                "total_reward": int(total_reward),
                "renters_pool_bps": int(renters_pool_bps),
                "renters_pool": int(renters_pool),
                "operator_pool": int(operator_pool),
                "sla_uptime": float(bot.uptime_score),
                "distributed": {},
            }

        # SLA multiplier: renters_pool scaled by uptime; remainder goes to operator.
        sla_mult = float(bot.uptime_score)
        renters_pool_sla = int(renters_pool * sla_mult)
        operator_pool += (renters_pool - renters_pool_sla)

        total_share = sum(int(l[1]["share_bps"]) for l in leases)
        distributed: Dict[str, int] = {}

        if total_share > 0 and renters_pool_sla > 0:
            for _, lease in leases:
                renter = lease["renter_id"]
                sbps = int(lease["share_bps"])
                amt = (renters_pool_sla * sbps) // total_share
                if amt <= 0:
                    continue
                self.state["balances"][renter] = int(self.state["balances"].get(renter, 0)) + int(amt)
                distributed[renter] = distributed.get(renter, 0) + int(amt)

        self.save()
        return {
            "bot_id": bot.bot_id,
            "total_reward": int(total_reward),
            "renters_pool_bps": int(renters_pool_bps),
            "renters_pool": int(renters_pool),
            "renters_pool_after_sla": int(renters_pool_sla),
            "operator_pool": int(operator_pool),
            "sla_uptime": float(bot.uptime_score),
            "distributed": distributed,
        }

    def balance(self, renter_id: str) -> int:
        return int(self.state["balances"].get(renter_id, 0))

    def list_leases(self, renter_id: Optional[str] = None) -> List[Dict[str, Any]]:
        out = []
        for lid, lease in self.state["leases"].items():
            if renter_id and lease.get("renter_id") != renter_id:
                continue
            out.append({"lease_id": lid, **lease})
        out.sort(key=lambda x: x.get("created_ts", 0), reverse=True)
        return out


# ----------------------------
# Patch ChainDB: privacy receipts + spot pricing + SLA payouts
# ----------------------------

def tx_sender(tx: "aichain.Transaction") -> str:
    if not tx.vin:
        return ""
    return tx.vin[0].from_addr or ""

def tx_guardian_dict(tx: "aichain.Transaction", burst_score: float) -> Dict[str, Any]:
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

def install_patch(
    guardian_model_path: str,
    threshold: float,
    fleet: FleetState,
    burst: BurstTracker,
    market: RentalMarket,
    privacy_mode: str,
    log_path: Optional[str] = None,
) -> Tuple[bool, str]:
    model = aiguardian.LogisticModel.load(guardian_model_path)
    guardian = aiguardian.Guardian(model, threshold=threshold)

    original_add = aichain.ChainDB.add_tx_to_mempool
    original_build_tpl = aichain.ChainDB.build_block_template
    original_submit = aichain.ChainDB.submit_block

    def _log(obj: Dict[str, Any]):
        if not log_path:
            return
        ensure_dir(log_path)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")

    def guarded_add(self: "aichain.ChainDB", tx: "aichain.Transaction"):
        if not hasattr(self, "quarantine"):
            self.quarantine = {}  # type: ignore[attr-defined]

        if len(tx.vin) == 1 and tx.vin[0].from_addr == "COINBASE":
            return original_add(self, tx)

        ts = now_ts()
        sender = tx_sender(tx)
        bscore = burst.observe(sender, ts)

        txd = tx_guardian_dict(tx, burst_score=bscore)
        feats = aiguardian.extract_features(txd)
        gscore = guardian.score(txd)

        committee = fleet.committee()
        votes = {"allow": 0, "deny": 0, "quarantine": 0}
        reasons: Dict[str, int] = {}
        for bot in committee:
            bot.heartbeat()
            min_fee = bot.policy_min_fee(feats)
            decision, reason = bot.decide(gscore, threshold, min_fee, int(tx.fee))
            votes[decision] += 1
            reasons[reason] = reasons.get(reason, 0) + 1

        decision = max(votes.items(), key=lambda kv: kv[1])[0]
        top_reason = max(reasons.items(), key=lambda kv: kv[1])[0] if reasons else "ok"
        leader = max(committee, key=lambda b: b.score)

        if decision == "allow":
            ok, out = original_add(self, tx)
            if ok:
                leader.accepted += 1
                leader.improve_uptime(0.0005)
            else:
                leader.rejected += 1
                leader.degrade_uptime(0.0010)
            fleet.update_score(leader)
            fleet.save()
            _log({"ts": ts, "action": "allow", "txid": tx.txid(), "leader": leader.name, "votes": votes})
            return (ok, out)

        # privacy receipt (no public reason)
        receipt = make_receipt(tx.txid(), top_reason, bucket_score(float(gscore)))
        packet = {
            "status": "quarantined" if decision == "quarantine" else "rejected",
            "txid": tx.txid(),
            "receipt_commitment": receipt["receipt_commitment"],
            "receipt_proof": receipt["receipt_proof"],
            "note": receipt["note"],
        }

        # quarantine store without reason
        if decision == "quarantine":
            self.quarantine[tx.txid()] = tx.to_dict()  # type: ignore[attr-defined]
            leader.quarantined += 1
            leader.degrade_uptime(0.0008)
        else:
            leader.rejected += 1
            leader.degrade_uptime(0.0015)

        fleet.update_score(leader)
        fleet.save()

        if privacy_mode == "reveal_to_sender":
            # caller-only hints (not logged)
            packet["sender_notice"] = {
                "score_bucket": receipt["score_bucket"],
                "reason_code": receipt["reason_code"],
                "reveal_secret": receipt["reveal_secret"],
                "how_to_reduce_penalty": [
                    "Reduce ráfagas (burst).",
                    "Sube el fee si está muy bajo.",
                    "Evita patrones repetitivos, memos largos y muchos outputs.",
                ],
            }

        _log({
            "ts": ts,
            "action": packet["status"],
            "txid": tx.txid(),
            "leader": leader.name,
            "votes": votes,
            "receipt_commitment": packet["receipt_commitment"],
        })
        return (False, json.dumps(packet, ensure_ascii=False))

    def fleet_build_template(self: "aichain.ChainDB", miner_addr: str):
        miner = fleet.miner_of_round()
        miner.heartbeat()
        return original_build_tpl(self, miner.name)

    def wrapped_submit(self: "aichain.ChainDB", blk: "aichain.Block"):
        ok, why = original_submit(self, blk)
        if not ok:
            return (ok, why)

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
            bot.improve_uptime(0.0020)
            fleet.update_score(bot)
            fleet.save()

            # Spot quote based on chain congestion + demand
            mempool_size = int(len(self.mempool))
            active_leases = market.active_leases_count()
            quote = market.spot_quote(mempool_size=mempool_size, active_leases=active_leases, tier=bot.tier)

            alloc = market.allocate_reward(
                bot=bot,
                total_reward=int(paid),
                renters_pool_bps=int(quote["renters_pool_bps"]),
            )

            _log({
                "ts": now_ts(),
                "action": "reward_allocate",
                "miner_bot": bot.name,
                "miner_bot_id": bot.bot_id,
                "tier": bot.tier,
                "uptime": bot.uptime_score,
                "paid": int(paid),
                "fees": int(fees),
                "subsidy": int(subsidy),
                "spot_quote": quote,
                "allocation": alloc,
            })

        return (ok, why)

    aichain.ChainDB.add_tx_to_mempool = guarded_add  # type: ignore[attr-defined]
    aichain.ChainDB.build_block_template = fleet_build_template  # type: ignore[attr-defined]
    aichain.ChainDB.submit_block = wrapped_submit  # type: ignore[attr-defined]
    return True, "market+sla patch installed"


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

def cmd_stats(args, fleet: FleetState):
    top = sorted(fleet.bots, key=lambda b: b.score, reverse=True)[: args.top]
    rows = []
    for b in top:
        rows.append({
            "name": b.name,
            "role": b.role,
            "tier": b.tier,
            "score": round(b.score, 6),
            "uptime": round(b.uptime_score, 6),
            "mined": b.mined_blocks,
            "fees": b.earned_fees,
            "subsidy": b.earned_subsidy,
            "accepted": b.accepted,
            "rejected": b.rejected,
            "quarantined": b.quarantined,
        })
    print(json.dumps({"fleet_size": fleet.size, "top": rows}, indent=2, ensure_ascii=False))

def cmd_spot_quote(args, market: RentalMarket, fleet: FleetState):
    # Quote without needing to mine: user can see current pricing conditions
    # We approximate mempool_size with user-provided number for quoting.
    quote = market.spot_quote(mempool_size=args.mempool, active_leases=market.active_leases_count(), tier=args.tier)
    print(json.dumps({"quote": quote}, indent=2, ensure_ascii=False))

def cmd_lease_create(args, market: RentalMarket, fleet: FleetState):
    # Provide a quote at time of purchase
    quote = market.spot_quote(mempool_size=args.mempool, active_leases=market.active_leases_count(), tier=args.tier)
    lease_id = market.create_lease(args.renter, args.bot_id, args.share_bps, args.duration)
    print(json.dumps({
        "ok": True,
        "lease_id": lease_id,
        "renter": args.renter,
        "bot_id": args.bot_id,
        "share_bps": args.share_bps,
        "duration_sec": args.duration,
        "current_price_quote": quote,
    }, indent=2, ensure_ascii=False))

def cmd_lease_list(args, market: RentalMarket):
    leases = market.list_leases(renter_id=(args.renter or None))
    print(json.dumps({"leases": leases}, indent=2, ensure_ascii=False))

def cmd_lease_close(args, market: RentalMarket):
    ok = market.close_lease(args.lease_id)
    print(json.dumps({"ok": bool(ok), "lease_id": args.lease_id}, indent=2, ensure_ascii=False))

def cmd_renter_balance(args, market: RentalMarket):
    bal = market.balance(args.renter)
    print(json.dumps({"renter": args.renter, "balance": int(bal)}, indent=2, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser(prog="aichain_aifleet_market_sla")
    p.add_argument("--datadir", default="./aichain_data")
    p.add_argument("--guardian-model", required=True)
    p.add_argument("--threshold", type=float, default=0.7)

    p.add_argument("--fleet-state", default="./fleet_state.json")
    p.add_argument("--fleet-size", type=int, default=100000)
    p.add_argument("--fleet-seed", type=int, default=1337)
    p.add_argument("--committee-size", type=int, default=21)

    p.add_argument("--burst-state", default="./burst_state.json")
    p.add_argument("--burst-window", type=int, default=60)
    p.add_argument("--burst-max", type=int, default=10)

    p.add_argument("--market-state", default="./rental_state.json")
    p.add_argument("--privacy-mode", default="receipt_only", choices=["receipt_only", "reveal_to_sender"])
    p.add_argument("--log", default="", help="optional JSONL log")

    sp = p.add_subparsers(dest="cmd", required=True)

    s0 = sp.add_parser("init")
    s0.set_defaults(func=lambda a, f, m: cmd_init(a))

    s1 = sp.add_parser("send")
    s1.add_argument("from_addr")
    s1.add_argument("to_addr")
    s1.add_argument("amount", type=int)
    s1.add_argument("--fee", type=int, default=1000)
    s1.add_argument("--memo", default="")
    s1.set_defaults(func=lambda a, f, m: cmd_send(a))

    s2 = sp.add_parser("mine")
    s2.add_argument("any_miner_addr", help="ignored; fleet selects miner bot")
    s2.set_defaults(func=lambda a, f, m: cmd_mine(a))

    s3 = sp.add_parser("stats")
    s3.add_argument("--top", type=int, default=20)
    s3.set_defaults(func=lambda a, f, m: cmd_stats(a, f))

    # Spot quote & leases
    q = sp.add_parser("spot-quote")
    q.add_argument("--mempool", type=int, default=0)
    q.add_argument("--tier", default="Bronze", choices=TIERS)
    q.set_defaults(func=lambda a, f, m: cmd_spot_quote(a, m, f))

    l1 = sp.add_parser("lease-create")
    l1.add_argument("--renter", required=True)
    l1.add_argument("--bot-id", type=int, required=True)
    l1.add_argument("--share-bps", type=int, default=1000)
    l1.add_argument("--duration", type=int, default=3600)
    l1.add_argument("--mempool", type=int, default=0, help="for quoting at purchase time")
    l1.add_argument("--tier", default="Bronze", choices=TIERS, help="for quoting at purchase time")
    l1.set_defaults(func=lambda a, f, m: cmd_lease_create(a, m, f))

    l2 = sp.add_parser("lease-list")
    l2.add_argument("--renter", default="")
    l2.set_defaults(func=lambda a, f, m: cmd_lease_list(a, m))

    l3 = sp.add_parser("lease-close")
    l3.add_argument("--lease-id", required=True)
    l3.set_defaults(func=lambda a, f, m: cmd_lease_close(a, m))

    l4 = sp.add_parser("renter-balance")
    l4.add_argument("--renter", required=True)
    l4.set_defaults(func=lambda a, f, m: cmd_renter_balance(a, m))

    args = p.parse_args()

    fleet = FleetState(args.fleet_state, args.fleet_size, args.fleet_seed, args.committee_size)
    burst = BurstTracker.load(args.burst_state, args.burst_window, args.burst_max)
    market = RentalMarket(args.market_state)

    ok, msg = install_patch(
        guardian_model_path=args.guardian_model,
        threshold=args.threshold,
        fleet=fleet,
        burst=burst,
        market=market,
        privacy_mode=args.privacy_mode,
        log_path=(args.log or None),
    )
    if not ok:
        raise SystemExit(msg)

    args.func(args, fleet, market)

    burst.save(args.burst_state)


if __name__ == "__main__":
    main()
