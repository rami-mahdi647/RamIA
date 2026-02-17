#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AIChain Core (single-file)
- Downloadable local software (no hosting)
- CLI + Local Web UI (docs + control panel)
- Medium security (anti-tamper, API keys, anti-replay)
- AI fleet committee + guardian filter (uses aiguardian.py model)
- Marketplace: renters, spot orderbook, reserved contracts
- Metering (credits) + audit log hash-chain (tamper-evident)
- Privacy receipts (stub) for rejected/quarantined txs (upgradeable to real ZK)

Requirements:
  - aichain.py and aiguardian.py in same folder.
  - guardian_model.json created via aiguardian.py train.

Optional:
  - pip install cryptography   (encrypt state at rest)

Run:
  python3 aicore.py --guardian-model guardian_model.json node --web
  python3 aicore.py --guardian-model guardian_model.json init
  python3 aicore.py --guardian-model guardian_model.json send genesis alice 100000 --fee 1000
  python3 aicore.py --guardian-model guardian_model.json mine x
"""

import argparse
import dataclasses
import hashlib
import hmac
import json
import os
import random
import secrets
import socketserver
import stat
import threading
import time
from http.server import BaseHTTPRequestHandler
from typing import Any, Dict, List, Optional, Tuple

import aichain
import aiguardian

# Optional encryption
try:
    from cryptography.fernet import Fernet  # type: ignore
    HAVE_FERNET = True
except Exception:
    HAVE_FERNET = False


# ============================================================
# Helpers
# ============================================================

TIERS = ["Bronze", "Silver", "Gold", "Platinum"]

def now_ts() -> int:
    return int(time.time())

def jcanon(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")

def h256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def ensure_dir(path: str):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)

def chmod_600_best_effort(path: str):
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass

def clamp_int(x: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(x)))

def clamp_float(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


# ============================================================
# Medium Security: Master secret, API keys, anti-replay, state HMAC, optional encryption
# ============================================================

class SecurityManager:
    def __init__(self, secret_file: str, replay_ttl_sec: int = 600, allow_clock_skew_sec: int = 120):
        self.secret_file = secret_file
        self.replay_ttl = int(replay_ttl_sec)
        self.clock_skew = int(allow_clock_skew_sec)
        self.master = self._load_or_create_master()
        self.nonce_store: Dict[str, int] = {}  # nonce -> ts_seen

        self.fernet: Optional["Fernet"] = None
        if HAVE_FERNET:
            import base64
            key = hashlib.sha256(self.master).digest()
            fkey = base64.urlsafe_b64encode(key)
            try:
                self.fernet = Fernet(fkey)
            except Exception:
                self.fernet = None

    def _load_or_create_master(self) -> bytes:
        ensure_dir(self.secret_file)
        if os.path.exists(self.secret_file):
            with open(self.secret_file, "rb") as f:
                data = f.read().strip()
            if len(data) >= 32:
                return data

        master = secrets.token_bytes(32)
        tmp = self.secret_file + ".tmp"
        with open(tmp, "wb") as f:
            f.write(master)
        os.replace(tmp, self.secret_file)
        chmod_600_best_effort(self.secret_file)
        return master

    def hmac_hex(self, msg: bytes) -> str:
        return hmac.new(self.master, msg, hashlib.sha256).hexdigest()

    # ---- API key storage ----
    def api_key_hash(self, renter: str, api_key: str, salt: Optional[bytes]) -> str:
        if salt is None:
            salt = secrets.token_bytes(16)
        dk = hashlib.pbkdf2_hmac("sha256", (renter + ":" + api_key).encode("utf-8"), salt, 200_000)
        return f"pbkdf2${salt.hex()}${dk.hex()}"

    def verify_api_key(self, renter: str, api_key: str, expected: str) -> bool:
        try:
            parts = expected.split("$")
            if len(parts) != 3 or parts[0] != "pbkdf2":
                return False
            salt = bytes.fromhex(parts[1])
            want = parts[2]
            got = self.api_key_hash(renter, api_key, salt).split("$")[2]
            return hmac.compare_digest(want, got)
        except Exception:
            return False

    # ---- Signed requests (HMAC) + anti-replay ----
    def sign_request(self, renter: str, ts: int, nonce: str, action: str, payload: Dict[str, Any]) -> str:
        ph = h256(jcanon(payload))
        msg = f"{renter}|{ts}|{nonce}|{action}|{ph}".encode("utf-8")
        return self.hmac_hex(msg)

    def _gc_nonces(self, now: int):
        cutoff = now - self.replay_ttl
        dead = [n for n, t in self.nonce_store.items() if t < cutoff]
        for n in dead:
            self.nonce_store.pop(n, None)

    def verify_signed_payload(self, renter: str, api_key: str, expected_api_hash: str,
                              action: str, payload: Dict[str, Any]) -> Tuple[bool, str]:
        try:
            ts = int(payload.get("_ts", 0))
            nonce = str(payload.get("_nonce", ""))
            sig = str(payload.get("_sig", ""))

            now = now_ts()
            if ts < now - self.replay_ttl or ts > now + self.clock_skew:
                return False, "timestamp_out_of_range"

            self._gc_nonces(now)
            if nonce in self.nonce_store:
                return False, "replayed_nonce"
            self.nonce_store[nonce] = now

            if not self.verify_api_key(renter, api_key, expected_api_hash):
                return False, "invalid_api_key"

            if len(sig) < 16:
                return False, "missing_signature"

            payload2 = dict(payload)
            payload2.pop("_sig", None)
            expected_sig = self.sign_request(renter, ts, nonce, action, payload2)
            if not hmac.compare_digest(sig, expected_sig):
                return False, "bad_signature"

            return True, "ok"
        except Exception:
            return False, "bad_request"

    # ---- State seal/unseal ----
    def seal(self, plaintext: bytes) -> bytes:
        if self.fernet:
            try:
                return self.fernet.encrypt(plaintext)
            except Exception:
                return plaintext
        return plaintext

    def unseal(self, blob: bytes) -> bytes:
        if self.fernet:
            try:
                return self.fernet.decrypt(blob)
            except Exception:
                return blob
        return blob

    def state_mac(self, state_bytes: bytes) -> str:
        return self.hmac_hex(state_bytes)


# ============================================================
# Audit log: hash-chained JSONL (tamper-evident)
# ============================================================

class AuditLog:
    def __init__(self, path: str):
        self.path = path
        self.last_hash = "0" * 64
        if os.path.exists(path):
            self._load_last()

    def _load_last(self):
        try:
            with open(self.path, "rb") as f:
                lines = f.read().splitlines()
            if not lines:
                return
            obj = json.loads(lines[-1].decode("utf-8"))
            self.last_hash = str(obj.get("_h", self.last_hash))
        except Exception:
            pass

    def append(self, event: Dict[str, Any]):
        ensure_dir(self.path)
        base = dict(event)
        base["_prev"] = self.last_hash
        base["_ts"] = now_ts()
        h = h256(jcanon(base))
        base["_h"] = h
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(base, ensure_ascii=False, sort_keys=True) + "\n")
        self.last_hash = h
        chmod_600_best_effort(self.path)

    def verify(self) -> Dict[str, Any]:
        """
        Offline verification: checks the chain of hashes.
        """
        if not os.path.exists(self.path):
            return {"ok": True, "events": 0, "note": "no log"}
        prev = "0" * 64
        n = 0
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    got_h = obj.get("_h", "")
                    got_prev = obj.get("_prev", "")
                    if got_prev != prev:
                        return {"ok": False, "events": n, "error": "broken_prev_link"}
                    obj2 = dict(obj)
                    obj2.pop("_h", None)
                    want_h = h256(jcanon(obj2))
                    if got_h != want_h:
                        return {"ok": False, "events": n, "error": "hash_mismatch"}
                    prev = got_h
                    n += 1
            return {"ok": True, "events": n}
        except Exception:
            return {"ok": False, "events": n, "error": "read_failed"}


# ============================================================
# Burst tracking
# ============================================================

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
        chmod_600_best_effort(path)


# ============================================================
# Fleet (committee + tier + uptime)
# ============================================================

def tier_from_score(score: float) -> str:
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
    uptime_score: float = 0.98

    accepted: int = 0
    rejected: int = 0
    quarantined: int = 0

    mined_blocks: int = 0
    earned_fees: int = 0
    earned_subsidy: int = 0

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
            self.bots.append(AIBot(bot_id=i, name=name, role=role, genome=genome))

    def save(self):
        ensure_dir(self.path)
        tmp = self.path + ".tmp"
        obj = {
            "version": 1,
            "size": self.size,
            "seed": self.seed,
            "committee_size": self.committee_size,
            "bots": [dataclasses.asdict(b) | {"genome": dataclasses.asdict(b.genome)} for b in self.bots],
        }
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False))
        os.replace(tmp, self.path)
        chmod_600_best_effort(self.path)

    def load(self):
        with open(self.path, "r", encoding="utf-8") as f:
            obj = json.loads(f.read())
        self.size = int(obj.get("size", self.size))
        self.seed = int(obj.get("seed", self.seed))
        self.committee_size = int(obj.get("committee_size", self.committee_size))
        self.bots = []
        for bd in obj.get("bots", []):
            g = BotGenome(**{k: float(v) for k, v in bd["genome"].items()})
            b = AIBot(
                bot_id=int(bd["bot_id"]),
                name=str(bd["name"]),
                role=str(bd["role"]),
                genome=g,
                score=float(bd.get("score", 0.0)),
                tier=str(bd.get("tier", "Bronze")),
                uptime_score=float(bd.get("uptime_score", 0.98)),
                accepted=int(bd.get("accepted", 0)),
                rejected=int(bd.get("rejected", 0)),
                quarantined=int(bd.get("quarantined", 0)),
                mined_blocks=int(bd.get("mined_blocks", 0)),
                earned_fees=int(bd.get("earned_fees", 0)),
                earned_subsidy=int(bd.get("earned_subsidy", 0)),
            )
            self.bots.append(b)
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


# ============================================================
# Secure state store (HMAC + optional encryption)
# ============================================================

class SecureStateStore:
    def __init__(self, path: str, sec: SecurityManager, audit: AuditLog, tag: str):
        self.path = path
        self.sec = sec
        self.audit = audit
        self.tag = tag

    def save(self, obj: Dict[str, Any]):
        ensure_dir(self.path)
        raw = jcanon(obj)
        mac = self.sec.state_mac(raw)
        envelope = {"mac": mac, "blob": raw.decode("utf-8")}
        data = jcanon(envelope)
        sealed = self.sec.seal(data)
        tmp = self.path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(sealed)
        os.replace(tmp, self.path)
        chmod_600_best_effort(self.path)
        self.audit.append({"type": "state_save", "tag": self.tag, "mac": mac})

    def load(self, default_obj: Dict[str, Any]) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            self.save(default_obj)
            return default_obj
        try:
            with open(self.path, "rb") as f:
                sealed = f.read()
            data = self.sec.unseal(sealed)
            env = json.loads(data.decode("utf-8"))
            mac = str(env.get("mac", ""))
            blob = str(env.get("blob", ""))
            raw = blob.encode("utf-8")
            want = self.sec.state_mac(raw)
            if not hmac.compare_digest(mac, want):
                self.audit.append({"type": "tamper_detected", "tag": self.tag, "mac": mac, "want": want})
                raise ValueError("STATE_TAMPER_DETECTED")
            return json.loads(raw.decode("utf-8"))
        except Exception:
            self.audit.append({"type": "state_load_failed", "tag": self.tag})
            return default_obj


# ============================================================
# Marketplace (renters + reserved + orderbook + credits + payouts)
# ============================================================

class Market:
    def __init__(self, path: str, sec: SecurityManager, audit: AuditLog):
        self.sec = sec
        self.audit = audit
        self.store = SecureStateStore(path, sec, audit, tag="market")
        self.state = self.store.load({
            "version": 1,
            "renters": {},       # renter -> {api_hash, created_ts}
            "balances": {},      # renter -> earned
            "credits": {},       # renter -> credits
            "reserved": {},      # cid -> {...}
            "orders": {},        # oid -> {...}
            "tier_orders": {t: [] for t in TIERS},
        })

    def save(self):
        self.store.save(self.state)

    # renters
    def renter_create(self, renter: str) -> Dict[str, Any]:
        if renter in self.state["renters"]:
            return {"ok": False, "error": "renter_exists"}
        api_key = secrets.token_urlsafe(32)
        api_hash = self.sec.api_key_hash(renter, api_key, salt=None)
        self.state["renters"][renter] = {"api_hash": api_hash, "created_ts": now_ts()}
        self.state["balances"].setdefault(renter, 0)
        self.state["credits"].setdefault(renter, 0)
        self.save()
        self.audit.append({"type": "renter_create", "renter": renter})
        return {"ok": True, "renter": renter, "api_key": api_key}

    def api_hash(self, renter: str) -> Optional[str]:
        r = self.state["renters"].get(renter)
        if not r:
            return None
        return str(r.get("api_hash", ""))

    # credits
    def add_credits(self, renter: str, credits: int):
        self.state["credits"][renter] = int(self.state["credits"].get(renter, 0)) + int(max(0, credits))
        self.save()

    def consume_credits(self, renter: str, cost: int) -> bool:
        cost = int(max(0, cost))
        cur = int(self.state["credits"].get(renter, 0))
        if cur < cost:
            return False
        self.state["credits"][renter] = cur - cost
        return True

    def credit_cost_for_service_unit(self, tier: str) -> int:
        return {"Bronze": 1, "Silver": 2, "Gold": 3, "Platinum": 4}.get(tier, 1)

    # reserved
    def reserved_create(self, renter: str, tier: str, renters_pool_bps: int, duration_sec: int, credits: int) -> str:
        cid = h256(jcanon({"r": renter, "tier": tier, "t": now_ts(), "n": os.urandom(8).hex()}))[:16]
        self.state["reserved"][cid] = {
            "renter": renter,
            "tier": tier,
            "renters_pool_bps": clamp_int(renters_pool_bps, 0, 10000),
            "expires_ts": now_ts() + int(max(60, duration_sec)),
            "created_ts": now_ts(),
        }
        self.add_credits(renter, int(max(0, credits)))
        self.save()
        self.audit.append({"type": "reserved_create", "renter": renter, "tier": tier, "cid": cid})
        return cid

    def reserved_active_for_tier(self, tier: str) -> List[Dict[str, Any]]:
        out = []
        for cid, c in self.state["reserved"].items():
            if c.get("tier") == tier and int(c.get("expires_ts", 0)) > now_ts():
                out.append({"contract_id": cid, **c})
        out.sort(key=lambda x: (-int(x.get("renters_pool_bps", 0)), int(x.get("created_ts", 0))))
        return out

    # orderbook
    def order_place(self, renter: str, tier: str, bid_bps: int, max_credits: int) -> str:
        oid = h256(jcanon({"r": renter, "tier": tier, "t": now_ts(), "n": os.urandom(8).hex()}))[:16]
        self.state["orders"][oid] = {
            "renter": renter,
            "tier": tier,
            "bid_bps": clamp_int(bid_bps, 0, 10000),
            "max_credits": int(max(0, max_credits)),
            "spent_credits": 0,
            "created_ts": now_ts(),
            "active": True,
        }
        self.state["tier_orders"].setdefault(tier, []).append(oid)
        self.save()
        self.audit.append({"type": "order_place", "renter": renter, "tier": tier, "oid": oid, "bid_bps": bid_bps})
        return oid

    def order_cancel(self, renter: str, oid: str) -> bool:
        o = self.state["orders"].get(oid)
        if not o or o.get("renter") != renter:
            return False
        o["active"] = False
        self.save()
        self.audit.append({"type": "order_cancel", "renter": renter, "oid": oid})
        return True

    def top_orders(self, tier: str, k: int = 3) -> List[Tuple[str, Dict[str, Any]]]:
        ids = self.state["tier_orders"].get(tier, [])
        active = []
        for oid in ids:
            o = self.state["orders"].get(oid)
            if not o or not o.get("active"):
                continue
            if int(o.get("spent_credits", 0)) >= int(o.get("max_credits", 0)):
                continue
            active.append((oid, o))
        active.sort(key=lambda x: (-int(x[1].get("bid_bps", 0)), int(x[1].get("created_ts", 0))))
        return active[:k]

    # payouts
    def allocate_reward(self, winners: List[str], amount: int) -> Dict[str, int]:
        alloc: Dict[str, int] = {}
        if not winners or amount <= 0:
            return alloc
        share = int(amount) // len(winners)
        for r in winners:
            self.state["balances"][r] = int(self.state["balances"].get(r, 0)) + share
            alloc[r] = alloc.get(r, 0) + share
        self.save()
        return alloc


# ============================================================
# Privacy receipt (stub; upgradeable to real ZK)
# ============================================================

def bucket_score(score: float) -> str:
    if score >= 0.90: return "very_high"
    if score >= 0.70: return "high"
    if score >= 0.50: return "med"
    return "low"

def make_privacy_receipt(txid: str, reason_code: str, score_bucket: str) -> Dict[str, Any]:
    secret = os.urandom(16).hex()
    payload = {"txid": txid, "ts": now_ts(), "reason": reason_code, "bucket": score_bucket, "secret": secret}
    commitment = h256(jcanon(payload))
    proof_stub = h256(("proof:" + commitment).encode("utf-8"))
    return {
        "receipt_commitment": commitment,
        "receipt_proof": proof_stub,
        "reveal_secret": secret,
        "reason_code": reason_code,
        "score_bucket": score_bucket,
    }


# ============================================================
# Chain patch: guardian + committee + metering + payouts
# ============================================================

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

def install_patch(guardian_model: str, threshold: float,
                  fleet: FleetState, burst: BurstTracker,
                  market: Market, audit: AuditLog,
                  privacy_mode: str) -> Tuple[bool, str]:
    model = aiguardian.LogisticModel.load(guardian_model)
    guardian = aiguardian.Guardian(model, threshold=threshold)

    original_add = aichain.ChainDB.add_tx_to_mempool
    original_build_tpl = aichain.ChainDB.build_block_template
    original_submit = aichain.ChainDB.submit_block

    def guarded_add(self: "aichain.ChainDB", tx: "aichain.Transaction"):
        if not hasattr(self, "quarantine"):
            self.quarantine = {}  # type: ignore[attr-defined]

        # coinbase bypass
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
            min_fee = bot.policy_min_fee(feats)
            decision, reason = bot.decide(gscore, threshold, min_fee, int(tx.fee))
            votes[decision] += 1
            reasons[reason] = reasons.get(reason, 0) + 1

        decision = max(votes.items(), key=lambda kv: kv[1])[0]
        top_reason = max(reasons.items(), key=lambda kv: kv[1])[0] if reasons else "ok"
        leader = max(committee, key=lambda b: b.score)

        # Metering: attribute 1 service-unit to reserved/top order for leader tier (if exists)
        tier = leader.tier
        cost = market.credit_cost_for_service_unit(tier)
        winner = None
        src = None

        reserved = market.reserved_active_for_tier(tier)
        if reserved:
            winner = reserved[0]["renter"]
            src = "reserved"
        else:
            top = market.top_orders(tier, k=1)
            if top:
                oid, o = top[0]
                winner = o["renter"]
                src = f"spot:{oid}"

        if winner:
            if market.consume_credits(winner, cost):
                if src and src.startswith("spot:"):
                    oid = src.split(":", 1)[1]
                    o = market.state["orders"].get(oid)
                    if o:
                        o["spent_credits"] = int(o.get("spent_credits", 0)) + cost
                market.save()
                audit.append({"type": "meter_service", "txid": tx.txid(), "tier": tier, "winner": winner, "cost": cost, "src": src})
            else:
                audit.append({"type": "meter_no_credits", "txid": tx.txid(), "tier": tier, "winner": winner, "cost": cost, "src": src})

        # decision
        if decision == "allow":
            ok, out = original_add(self, tx)
            if ok:
                leader.accepted += 1
                leader.uptime_score = clamp_float(leader.uptime_score + 0.0003, 0.0, 1.0)
            else:
                leader.rejected += 1
                leader.uptime_score = clamp_float(leader.uptime_score - 0.0010, 0.0, 1.0)
            fleet.update_score(leader)
            fleet.save()
            return (ok, out)

        # privacy receipt only
        r = make_privacy_receipt(tx.txid(), top_reason, bucket_score(float(gscore)))
        packet = {
            "status": "quarantined" if decision == "quarantine" else "rejected",
            "txid": tx.txid(),
            "receipt_commitment": r["receipt_commitment"],
            "receipt_proof": r["receipt_proof"],
            "note": "Privacy receipt (stub). Replace with real ZK proof later.",
        }

        if decision == "quarantine":
            self.quarantine[tx.txid()] = tx.to_dict()  # type: ignore[attr-defined]
            leader.quarantined += 1
            leader.uptime_score = clamp_float(leader.uptime_score - 0.0008, 0.0, 1.0)
        else:
            leader.rejected += 1
            leader.uptime_score = clamp_float(leader.uptime_score - 0.0012, 0.0, 1.0)

        fleet.update_score(leader)
        fleet.save()

        # reveal_to_sender gives private hints only to the caller (still not public)
        if privacy_mode == "reveal_to_sender":
            packet["sender_notice"] = {
                "score_bucket": r["score_bucket"],
                "reason_code": r["reason_code"],
                "reveal_secret": r["reveal_secret"],
                "hint": [
                    "Reduce ráfagas (burst).",
                    "Sube el fee si es muy bajo.",
                    "Evita memos largos y demasiados outputs.",
                ]
            }

        return (False, json.dumps(packet, ensure_ascii=False))

    def fleet_build_template(self: "aichain.ChainDB", miner_addr: str):
        miner = fleet.miner_of_round()
        return original_build_tpl(self, miner.name)

    def wrapped_submit(self: "aichain.ChainDB", blk: "aichain.Block"):
        ok, why = original_submit(self, blk)
        if not ok:
            return (ok, why)

        miner_addr = blk.txs[0].vout[0].to_addr if blk.txs and blk.txs[0].vout else ""
        paid = sum(o.amount for o in blk.txs[0].vout)
        fees = sum(t.fee for t in blk.txs[1:])
        subsidy = max(0, paid - fees)

        # locate bot
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
            bot.uptime_score = clamp_float(bot.uptime_score + 0.0015, 0.0, 1.0)
            fleet.update_score(bot)
            fleet.save()

            tier = bot.tier
            winners: List[str] = []
            renters_pool_bps = 0
            mode = "operator_only"

            reserved = market.reserved_active_for_tier(tier)
            if reserved:
                winners = [reserved[0]["renter"]]
                renters_pool_bps = int(reserved[0]["renters_pool_bps"])
                mode = "reserved"
            else:
                top = market.top_orders(tier, k=1)
                if top:
                    oid, o = top[0]
                    winners = [o["renter"]]
                    renters_pool_bps = int(o["bid_bps"])
                    mode = f"spot:{oid}"

            renters_pool = (int(paid) * int(renters_pool_bps)) // 10000
            operator_pool = int(paid) - renters_pool

            # SLA multiplier
            renters_pool_sla = int(renters_pool * float(bot.uptime_score))
            operator_pool += (renters_pool - renters_pool_sla)

            alloc = market.allocate_reward(winners, renters_pool_sla)
            audit.append({
                "type": "block_payout",
                "bot": bot.name,
                "tier": bot.tier,
                "uptime": bot.uptime_score,
                "paid": int(paid),
                "fees": int(fees),
                "subsidy": int(subsidy),
                "mode": mode,
                "renters_pool_bps": int(renters_pool_bps),
                "renters_pool_after_sla": int(renters_pool_sla),
                "operator_pool": int(operator_pool),
                "alloc": alloc,
            })

        return (ok, why)

    aichain.ChainDB.add_tx_to_mempool = guarded_add  # type: ignore[attr-defined]
    aichain.ChainDB.build_block_template = fleet_build_template  # type: ignore[attr-defined]
    aichain.ChainDB.submit_block = wrapped_submit  # type: ignore[attr-defined]

    return True, "patch installed"


# ============================================================
# Local Web UI (docs + panel) - runs only on localhost
# ============================================================

DOCS_HTML = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>AIChain Core — Local Node</title>
<style>
  body{font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial; margin:0; background:#0b0f14; color:#e8eef6;}
  header{padding:18px 20px; border-bottom:1px solid #1b2633; background:#0b0f14; position:sticky; top:0;}
  h1{margin:0; font-size:18px;}
  .wrap{max-width:1100px; margin:0 auto; padding:18px 20px;}
  .grid{display:grid; grid-template-columns: 1.2fr 0.8fr; gap:14px;}
  .card{background:#0f1620; border:1px solid #1b2633; border-radius:14px; padding:14px;}
  h2{margin:0 0 8px 0; font-size:16px;}
  p{margin:8px 0; color:#cdd9e5; line-height:1.45;}
  code, pre{background:#0b0f14; border:1px solid #1b2633; border-radius:10px; padding:10px; color:#d9f99d;}
  pre{overflow:auto;}
  .row{display:flex; gap:8px; flex-wrap:wrap; margin:10px 0;}
  input, select, button{background:#0b0f14; border:1px solid #1b2633; color:#e8eef6; border-radius:10px; padding:10px; font-size:13px;}
  button{cursor:pointer;}
  button:hover{border-color:#2b3b52;}
  .muted{color:#9fb1c1; font-size:12px;}
  .out{white-space:pre-wrap; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas; font-size:12px; color:#e8eef6;}
  .tag{display:inline-block; padding:3px 8px; border:1px solid #1b2633; border-radius:999px; font-size:12px; color:#9fb1c1;}
  a{color:#9dd6ff;}
</style>
</head>
<body>
<header>
  <div class="wrap" style="display:flex;justify-content:space-between;align-items:center;gap:10px;">
    <h1>AIChain Core — nodo local (descargable)</h1>
    <span class="tag">localhost</span>
  </div>
</header>

<div class="wrap">
  <div class="grid">
    <div class="card">
      <h2>¿Qué es esto?</h2>
      <p>
        <b>AIChain</b> es una blockchain experimental inspirada en Bitcoin, pero con:
      </p>
      <ul>
        <li><b>Comité IA</b> (flota de bots) que decide admisión de transacciones y políticas.</li>
        <li><b>Guardian</b> (modelo ML) que puntúa riesgo de spam/abuso (tú entrenas el modelo).</li>
        <li><b>Marketplace</b> estilo “GPU renting”: la gente alquila capacidad (bots/tier) y participa en rewards.</li>
        <li><b>Privacidad media</b>: rechazos devuelven “recibos opacos” (stub de ZK) sin exponer motivos públicamente.</li>
        <li><b>Seguridad media</b>: API keys, anti-replay, integridad HMAC del estado, audit log encadenado.</li>
      </ul>

      <h2>Flujo mental (como Bitcoin Core)</h2>
      <pre>1) init  -> crea el datadir y el chain local
2) send  -> crea TX y la propone al mempool (comité IA decide)
3) mine  -> mina un bloque (la flota elige minero) y reparte rewards (market)
4) renter/market -> crea renters, orders, reserved, credits
5) web UI -> docs + panel, pero el nodo sigue siendo CLI-first</pre>

      <h2>Notas de seguridad</h2>
      <p class="muted">
        - Todo corre en tu máquina. Esta UI solo escucha en 127.0.0.1.<br/>
        - Estado protegido con HMAC. Con <code>cryptography</code> se cifra (Fernet).<br/>
        - “ZK” aquí es stub: recibo opaco + compromiso. Cambiable a SNARK/STARK cuando quieras.
      </p>
    </div>

    <div class="card">
      <h2>Panel rápido</h2>
      <div class="row">
        <button onclick="api('/api/status', {})">Status</button>
        <button onclick="api('/api/init', {})">Init</button>
        <button onclick="api('/api/mine', {any_miner_addr:'x'})">Mine</button>
        <button onclick="api('/api/audit_verify', {})">Audit verify</button>
      </div>

      <h2>Send TX</h2>
      <div class="row">
        <input id="from" placeholder="from" value="genesis"/>
        <input id="to" placeholder="to" value="alice"/>
      </div>
      <div class="row">
        <input id="amt" placeholder="amount" value="100000"/>
        <input id="fee" placeholder="fee" value="1000"/>
      </div>
      <div class="row">
        <input id="memo" placeholder="memo (opcional)" value="hola"/>
        <button onclick="sendTx()">Send</button>
      </div>

      <h2>Marketplace</h2>
      <p class="muted">Para acciones de market necesitas <b>renter + api_key</b> (en CLI o aquí).</p>
      <div class="row">
        <input id="renter" placeholder="renter" value="alice"/>
        <input id="apikey" placeholder="api_key" value=""/>
      </div>
      <div class="row">
        <button onclick="api('/api/renter_create', {renter: val('renter')})">Create renter</button>
        <button onclick="api('/api/renter_status', {renter: val('renter'), api_key: val('apikey')})">Renter status</button>
      </div>
      <div class="row">
        <select id="tier">
          <option>Bronze</option><option>Silver</option><option selected>Gold</option><option>Platinum</option>
        </select>
        <input id="bid" placeholder="bid_bps" value="7000"/>
        <input id="maxc" placeholder="max_credits" value="3000"/>
        <button onclick="api('/api/order_place', {renter:val('renter'), api_key:val('apikey'), tier:val('tier'), bid_bps:parseInt(val('bid')), max_credits:parseInt(val('maxc'))})">Place spot order</button>
      </div>
      <div class="row">
        <input id="rp" placeholder="reserved renters_pool_bps" value="6500"/>
        <input id="dur" placeholder="duration_sec" value="3600"/>
        <input id="cred" placeholder="credits" value="5000"/>
        <button onclick="api('/api/reserved_create', {renter:val('renter'), api_key:val('apikey'), tier:val('tier'), renters_pool_bps:parseInt(val('rp')), duration_sec:parseInt(val('dur')), credits:parseInt(val('cred'))})">Create reserved</button>
      </div>

      <h2>Salida</h2>
      <div id="out" class="out">—</div>
    </div>
  </div>
</div>

<script>
function val(id){ return document.getElementById(id).value; }
async function api(path, body){
  const res = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  const txt = await res.text();
  try{ document.getElementById('out').textContent = JSON.stringify(JSON.parse(txt), null, 2); }
  catch(e){ document.getElementById('out').textContent = txt; }
}
function sendTx(){
  api('/api/send', {
    from_addr: val('from'),
    to_addr: val('to'),
    amount: parseInt(val('amt')),
    fee: parseInt(val('fee')),
    memo: val('memo'),
  });
}
</script>
</body>
</html>
"""


class AppContext:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.audit = AuditLog(args.audit_log)
        self.sec = SecurityManager(args.secret_file)
        self.fleet = FleetState(args.fleet_state, args.fleet_size, args.fleet_seed, args.committee_size)
        self.burst = BurstTracker.load(args.burst_state, args.burst_window, args.burst_max)
        self.market = Market(args.market_state, self.sec, self.audit)

        ok, msg = install_patch(
            guardian_model=args.guardian_model,
            threshold=args.threshold,
            fleet=self.fleet,
            burst=self.burst,
            market=self.market,
            audit=self.audit,
            privacy_mode=args.privacy_mode,
        )
        if not ok:
            raise SystemExit(msg)

    def db(self) -> "aichain.ChainDB":
        return aichain.ChainDB(self.args.datadir)

    def save(self):
        self.burst.save(self.args.burst_state)
        self.fleet.save()
        self.market.save()

    # ---- market auth helpers for web API ----
    def signed_payload(self, renter: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        ts = now_ts()
        nonce = secrets.token_hex(12)
        payload2 = dict(payload)
        payload2["_ts"] = ts
        payload2["_nonce"] = nonce
        sig = self.sec.sign_request(renter, ts, nonce, action, payload2)
        payload2["_sig"] = sig
        return payload2

    def require_market_auth(self, renter: str, api_key: str, action: str, payload: Dict[str, Any]) -> Tuple[bool, str]:
        api_hash = self.market.api_hash(renter)
        if not api_hash:
            return False, "unknown_renter"
        return self.sec.verify_signed_payload(renter, api_key, api_hash, action, payload)


class LocalHandler(BaseHTTPRequestHandler):
    ctx: AppContext = None  # type: ignore

    def _send(self, status: int, content_type: str, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(200, "text/html; charset=utf-8", DOCS_HTML.encode("utf-8"))
            return
        self._send(404, "text/plain; charset=utf-8", b"not found")

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            data = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            self._send(400, "application/json", json.dumps({"ok": False, "error": "bad_json"}).encode("utf-8"))
            return

        try:
            out = self.route(self.path, data)
            self._send(200, "application/json; charset=utf-8", json.dumps(out, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self._send(500, "application/json; charset=utf-8",
                       json.dumps({"ok": False, "error": "internal_error", "detail": str(e)}).encode("utf-8"))

    def route(self, path: str, data: Dict[str, Any]) -> Dict[str, Any]:
        ctx = self.ctx

        if path == "/api/status":
            db = ctx.db()
            return {
                "ok": True,
                "height": db.height(),
                "tip": db.tip().block_hash(),
                "mempool": len(db.mempool),
                "fleet_size": ctx.fleet.size,
                "security": {
                    "encrypted_state": bool(ctx.sec.fernet is not None),
                    "audit_log": ctx.args.audit_log,
                }
            }

        if path == "/api/init":
            db = ctx.db()
            return {"ok": True, "height": db.height(), "tip": db.tip().block_hash()}

        if path == "/api/send":
            db = ctx.db()
            tx = db.make_tx(
                str(data.get("from_addr", "")),
                str(data.get("to_addr", "")),
                int(data.get("amount", 0)),
                int(data.get("fee", 1000)),
                memo=str(data.get("memo", "")),
            )
            ok, out = db.add_tx_to_mempool(tx)
            ctx.save()
            if ok:
                return {"ok": True, "txid": out}
            try:
                return {"ok": False, "result": json.loads(out)}
            except Exception:
                return {"ok": False, "result": out}

        if path == "/api/mine":
            db = ctx.db()
            tpl = db.build_block_template(str(data.get("any_miner_addr", "x")))
            blk = db._mine_block(tpl)
            ok, why = db.submit_block(blk)
            ctx.save()
            if not ok:
                return {"ok": False, "error": why}
            return {
                "ok": True,
                "height": db.height(),
                "hash": blk.block_hash(),
                "coinbase_to": blk.txs[0].vout[0].to_addr if blk.txs and blk.txs[0].vout else "",
                "coinbase_paid": sum(o.amount for o in blk.txs[0].vout) if blk.txs and blk.txs[0].vout else 0,
            }

        if path == "/api/audit_verify":
            return ctx.audit.verify()

        # Marketplace public: create renter
        if path == "/api/renter_create":
            renter = str(data.get("renter", ""))
            if not renter:
                return {"ok": False, "error": "missing_renter"}
            out = ctx.market.renter_create(renter)
            ctx.save()
            out["security_note"] = ("encrypted_state+HMAC" if ctx.sec.fernet else "HMAC_only (install cryptography for encryption)")
            return out

        # Marketplace protected
        if path == "/api/renter_status":
            renter = str(data.get("renter", ""))
            api_key = str(data.get("api_key", ""))
            payload = ctx.signed_payload(renter, "renter_status", {"action": "renter_status"})
            ok, reason = ctx.require_market_auth(renter, api_key, "renter_status", payload)
            if not ok:
                return {"ok": False, "error": reason}
            return {
                "ok": True,
                "renter": renter,
                "balance": int(ctx.market.state["balances"].get(renter, 0)),
                "credits": int(ctx.market.state["credits"].get(renter, 0)),
                "active_orders": [
                    {"order_id": oid, **o}
                    for oid, o in ctx.market.state["orders"].items()
                    if o.get("renter") == renter and o.get("active")
                ],
                "active_reserved": [
                    {"contract_id": cid, **c}
                    for cid, c in ctx.market.state["reserved"].items()
                    if c.get("renter") == renter and int(c.get("expires_ts", 0)) > now_ts()
                ]
            }

        if path == "/api/order_place":
            renter = str(data.get("renter", ""))
            api_key = str(data.get("api_key", ""))
            tier = str(data.get("tier", "Gold"))
            bid_bps = int(data.get("bid_bps", 7000))
            max_credits = int(data.get("max_credits", 1000))
            payload = ctx.signed_payload(renter, "order_place", {"tier": tier, "bid_bps": bid_bps, "max_credits": max_credits})
            ok, reason = ctx.require_market_auth(renter, api_key, "order_place", payload)
            if not ok:
                return {"ok": False, "error": reason}
            if tier not in TIERS:
                return {"ok": False, "error": "bad_tier"}
            oid = ctx.market.order_place(renter, tier, bid_bps, max_credits)
            ctx.audit.append({"type": "api_order_place", "renter": renter, "tier": tier, "oid": oid})
            ctx.save()
            return {"ok": True, "order_id": oid}

        if path == "/api/reserved_create":
            renter = str(data.get("renter", ""))
            api_key = str(data.get("api_key", ""))
            tier = str(data.get("tier", "Gold"))
            renters_pool_bps = int(data.get("renters_pool_bps", 6500))
            duration_sec = int(data.get("duration_sec", 3600))
            credits = int(data.get("credits", 5000))
            payload = ctx.signed_payload(renter, "reserved_create", {
                "tier": tier, "renters_pool_bps": renters_pool_bps, "duration_sec": duration_sec, "credits": credits
            })
            ok, reason = ctx.require_market_auth(renter, api_key, "reserved_create", payload)
            if not ok:
                return {"ok": False, "error": reason}
            if tier not in TIERS:
                return {"ok": False, "error": "bad_tier"}
            cid = ctx.market.reserved_create(renter, tier, renters_pool_bps, duration_sec, credits)
            ctx.audit.append({"type": "api_reserved_create", "renter": renter, "tier": tier, "cid": cid})
            ctx.save()
            return {"ok": True, "contract_id": cid}

        return {"ok": False, "error": "unknown_endpoint"}


def run_web(ctx: AppContext, host: str, port: int):
    class ThreadingHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True

    LocalHandler.ctx = ctx
    httpd = ThreadingHTTPServer((host, port), LocalHandler)
    print(f"[web] http://{host}:{port}")
    httpd.serve_forever()


# ============================================================
# CLI Commands
# ============================================================

def cmd_init(args, ctx: AppContext):
    db = ctx.db()
    print("ok")
    print("height", db.height())
    print("tip", db.tip().block_hash())

def cmd_send(args, ctx: AppContext):
    db = ctx.db()
    tx = db.make_tx(args.from_addr, args.to_addr, args.amount, args.fee, memo=args.memo)
    ok, out = db.add_tx_to_mempool(tx)
    ctx.save()
    if ok:
        print("txid", out)
        return
    try:
        print(json.dumps(json.loads(out), indent=2, ensure_ascii=False))
    except Exception:
        print("error", out)

def cmd_mine(args, ctx: AppContext):
    db = ctx.db()
    tpl = db.build_block_template(args.any_miner_addr)  # ignored
    mined = db._mine_block(tpl)
    ok, why = db.submit_block(mined)
    ctx.save()
    if not ok:
        print("error", why)
        return
    print("ok accepted")
    print("height", db.height())
    print("hash", mined.block_hash())
    print("coinbase_to", mined.txs[0].vout[0].to_addr if mined.txs and mined.txs[0].vout else "")
    print("coinbase_paid", sum(o.amount for o in mined.txs[0].vout) if mined.txs and mined.txs[0].vout else 0)

def cmd_stats(args, ctx: AppContext):
    top = sorted(ctx.fleet.bots, key=lambda b: b.score, reverse=True)[: args.top]
    rows = []
    for b in top:
        rows.append({
            "name": b.name, "role": b.role, "tier": b.tier,
            "score": round(b.score, 6),
            "uptime": round(b.uptime_score, 6),
            "mined": b.mined_blocks,
            "accepted": b.accepted,
            "rejected": b.rejected,
            "quarantined": b.quarantined,
        })
    print(json.dumps({"fleet_size": ctx.fleet.size, "top": rows}, indent=2, ensure_ascii=False))

def cmd_renter_create(args, ctx: AppContext):
    out = ctx.market.renter_create(args.renter)
    ctx.save()
    print(json.dumps(out, indent=2, ensure_ascii=False))

def cmd_audit_verify(args, ctx: AppContext):
    print(json.dumps(ctx.audit.verify(), indent=2, ensure_ascii=False))

def cmd_renter_status(args, ctx: AppContext):
    api_hash = ctx.market.api_hash(args.renter)
    if not api_hash or not ctx.sec.verify_api_key(args.renter, args.api_key, api_hash):
        print(json.dumps({"ok": False, "error": "invalid_api_key"}, indent=2, ensure_ascii=False))
        return
    print(json.dumps({
        "ok": True,
        "renter": args.renter,
        "balance": int(ctx.market.state["balances"].get(args.renter, 0)),
        "credits": int(ctx.market.state["credits"].get(args.renter, 0)),
    }, indent=2, ensure_ascii=False))

def cmd_order_place(args, ctx: AppContext):
    api_hash = ctx.market.api_hash(args.renter)
    if not api_hash or not ctx.sec.verify_api_key(args.renter, args.api_key, api_hash):
        print(json.dumps({"ok": False, "error": "invalid_api_key"}, indent=2, ensure_ascii=False))
        return
    oid = ctx.market.order_place(args.renter, args.tier, args.bid_bps, args.max_credits)
    ctx.audit.append({"type": "cli_order_place", "renter": args.renter, "tier": args.tier, "oid": oid})
    ctx.save()
    print(json.dumps({"ok": True, "order_id": oid}, indent=2, ensure_ascii=False))

def cmd_reserved_create(args, ctx: AppContext):
    api_hash = ctx.market.api_hash(args.renter)
    if not api_hash or not ctx.sec.verify_api_key(args.renter, args.api_key, api_hash):
        print(json.dumps({"ok": False, "error": "invalid_api_key"}, indent=2, ensure_ascii=False))
        return
    cid = ctx.market.reserved_create(args.renter, args.tier, args.renters_pool_bps, args.duration_sec, args.credits)
    ctx.audit.append({"type": "cli_reserved_create", "renter": args.renter, "tier": args.tier, "cid": cid})
    ctx.save()
    print(json.dumps({"ok": True, "contract_id": cid}, indent=2, ensure_ascii=False))


# ============================================================
# Node mode: keep process alive; optional web; like "bitcoind"
# ============================================================

def cmd_node(args, ctx: AppContext):
    threads: List[threading.Thread] = []
    if args.web:
        t = threading.Thread(target=run_web, args=(ctx, args.web_host, args.web_port), daemon=True)
        t.start()
        threads.append(t)

    print("[node] running. Press Ctrl+C to stop.")
    print("[node] datadir:", args.datadir)
    print("[node] privacy_mode:", args.privacy_mode)
    print("[node] encrypted_state:", bool(ctx.sec.fernet))
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        ctx.save()
        print("[node] stopped.")


# ============================================================
# Main
# ============================================================

def main():
    p = argparse.ArgumentParser(prog="aicore")
    p.add_argument("--datadir", default="./aichain_data")
    p.add_argument("--guardian-model", required=True)
    p.add_argument("--threshold", type=float, default=0.7)
    p.add_argument("--privacy-mode", default="receipt_only", choices=["receipt_only", "reveal_to_sender"])

    p.add_argument("--fleet-state", default="./fleet_state.json")
    p.add_argument("--fleet-size", type=int, default=100000)
    p.add_argument("--fleet-seed", type=int, default=1337)
    p.add_argument("--committee-size", type=int, default=21)

    p.add_argument("--burst-state", default="./burst_state.json")
    p.add_argument("--burst-window", type=int, default=60)
    p.add_argument("--burst-max", type=int, default=10)

    p.add_argument("--market-state", default="./market_secure_state.bin")
    p.add_argument("--secret-file", default="./market_secret.key")
    p.add_argument("--audit-log", default="./audit_log.jsonl")

    sp = p.add_subparsers(dest="cmd", required=True)

    s0 = sp.add_parser("init")
    s0.set_defaults(handler=cmd_init)

    s1 = sp.add_parser("send")
    s1.add_argument("from_addr")
    s1.add_argument("to_addr")
    s1.add_argument("amount", type=int)
    s1.add_argument("--fee", type=int, default=1000)
    s1.add_argument("--memo", default="")
    s1.set_defaults(handler=cmd_send)

    s2 = sp.add_parser("mine")
    s2.add_argument("any_miner_addr")
    s2.set_defaults(handler=cmd_mine)

    s3 = sp.add_parser("stats")
    s3.add_argument("--top", type=int, default=20)
    s3.set_defaults(handler=cmd_stats)

    s4 = sp.add_parser("renter-create")
    s4.add_argument("--renter", required=True)
    s4.set_defaults(handler=cmd_renter_create)

    s5 = sp.add_parser("renter-status")
    s5.add_argument("--renter", required=True)
    s5.add_argument("--api-key", required=True)
    s5.set_defaults(handler=cmd_renter_status)

    s6 = sp.add_parser("order-place")
    s6.add_argument("--renter", required=True)
    s6.add_argument("--api-key", required=True)
    s6.add_argument("--tier", required=True, choices=TIERS)
    s6.add_argument("--bid-bps", type=int, required=True)
    s6.add_argument("--max-credits", type=int, default=1000)
    s6.set_defaults(handler=cmd_order_place)

    s7 = sp.add_parser("reserved-create")
    s7.add_argument("--renter", required=True)
    s7.add_argument("--api-key", required=True)
    s7.add_argument("--tier", required=True, choices=TIERS)
    s7.add_argument("--renters-pool-bps", type=int, default=6500)
    s7.add_argument("--duration-sec", type=int, default=3600)
    s7.add_argument("--credits", type=int, default=5000)
    s7.set_defaults(handler=cmd_reserved_create)

    s8 = sp.add_parser("audit-verify")
    s8.set_defaults(handler=cmd_audit_verify)

    node = sp.add_parser("node")
    node.add_argument("--web", action="store_true", help="start local web UI on localhost")
    node.add_argument("--web-host", default="127.0.0.1")
    node.add_argument("--web-port", type=int, default=8787)
    node.set_defaults(handler=cmd_node)

    args = p.parse_args()
    ctx = AppContext(args)
    args.handler(args, ctx)


if __name__ == "__main__":
    main()
