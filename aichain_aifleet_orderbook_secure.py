#!/usr/bin/env python3
# AIChain AI-Fleet Marketplace: OrderBook + Reserved/Spot + Metering + Medium Security (anti-hack)
#
# Single-file entrypoint. No edits to aichain.py / aiguardian.py.
#
# Features:
# - Order book (bids) per tier; spot allocation based on highest bids.
# - Reserved contracts (fixed terms).
# - Metering: renters consume credits for "service units" (tx screening/validation decisions).
# - Proof-of-Service (stub): tamper-evident receipts + hash-chained audit log.
# - Medium security:
#   * Renter API keys (HMAC) for marketplace actions
#   * Anti-replay: timestamp + nonce tracking
#   * State integrity: HMAC over serialized state (detect tampering)
#   * Optional encryption at rest if `cryptography` is available
#   * File permissions 0600 (best-effort)
#
# Quick start:
#   python3 aiguardian.py train --csv dataset.csv --out guardian_model.json
#   python3 aichain_aifleet_orderbook_secure.py --guardian-model guardian_model.json init
#
# Create renter:
#   python3 aichain_aifleet_orderbook_secure.py --guardian-model guardian_model.json renter-create --renter alice
#   (copy the api_key output; store it securely)
#
# Place spot bid:
#   python3 aichain_aifleet_orderbook_secure.py --guardian-model guardian_model.json \
#     --renter alice --api-key <KEY> order-place --tier Gold --bid-bps 6500 --max-credits 5000
#
# Mine:
#   python3 aichain_aifleet_orderbook_secure.py --guardian-model guardian_model.json mine x
#
# See renter balance/credits:
#   python3 aichain_aifleet_orderbook_secure.py --guardian-model guardian_model.json renter-status --renter alice --api-key <KEY>

import argparse
import dataclasses
import hashlib
import hmac
import json
import os
import random
import secrets
import stat
import time
from typing import Any, Dict, List, Optional, Tuple

import aichain
import aiguardian

# Optional encryption
try:
    from cryptography.fernet import Fernet  # type: ignore
    HAVE_FERNET = True
except Exception:
    HAVE_FERNET = False


# ----------------------------
# Helpers
# ----------------------------

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

def best_effort_chmod_600(path: str):
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass

def clamp_int(x: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(x)))

def clamp_float(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


# ----------------------------
# Security: master secret, HMAC, API keys, anti-replay, state integrity
# ----------------------------

class SecurityManager:
    """
    Medium security:
      - Master secret in secret_file (generated if missing)
      - Renter API keys: derived and stored as salted hash
      - Signed requests: HMAC(master, renter_id|ts|nonce|action|payload_hash)
      - Anti-replay: store used nonces for short TTL
      - State integrity: HMAC(master, serialized_state)
      - Optional encryption at rest (Fernet) if cryptography available
    """
    def __init__(self, secret_file: str, replay_ttl_sec: int = 600, allow_clock_skew_sec: int = 120):
        self.secret_file = secret_file
        self.replay_ttl = int(replay_ttl_sec)
        self.clock_skew = int(allow_clock_skew_sec)
        self.master = self._load_or_create_master()
        self.nonce_store: Dict[str, int] = {}  # nonce -> ts_seen

        # Fernet key derived from master (optional)
        self.fernet: Optional["Fernet"] = None
        if HAVE_FERNET:
            # Fernet key must be urlsafe base64 32 bytes; derive from master using sha256 then base64
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
        best_effort_chmod_600(self.secret_file)
        return master

    def hmac_hex(self, msg: bytes) -> str:
        return hmac.new(self.master, msg, hashlib.sha256).hexdigest()

    def sign_request(self, renter: str, ts: int, nonce: str, action: str, payload: Dict[str, Any]) -> str:
        ph = h256(jcanon(payload))
        msg = f"{renter}|{ts}|{nonce}|{action}|{ph}".encode("utf-8")
        return self.hmac_hex(msg)

    def verify_request(self, renter: str, api_key: str, ts: int, nonce: str, action: str, payload: Dict[str, Any], expected_api_hash: str) -> Tuple[bool, str]:
        # basic clock skew
        now = now_ts()
        if ts < now - self.replay_ttl or ts > now + self.clock_skew:
            return False, "timestamp_out_of_range"

        # anti-replay nonce
        self._gc_nonces(now)
        if nonce in self.nonce_store:
            return False, "replayed_nonce"
        self.nonce_store[nonce] = now

        # api key check (hash)
        api_hash = self.api_key_hash(renter, api_key, expected_salt=None)  # computed with embedded salt in expected hash format?
        # expected_api_hash format: "pbkdf2$<salt_hex>$<hash_hex>"
        ok, reason = self._verify_api_hash(renter, api_key, expected_api_hash)
        if not ok:
            return False, reason

        # signature check
        sig = payload.get("_sig", "")
        if not isinstance(sig, str) or len(sig) < 16:
            return False, "missing_signature"

        payload2 = dict(payload)
        payload2.pop("_sig", None)
        expected_sig = self.sign_request(renter, ts, nonce, action, payload2)
        if not hmac.compare_digest(sig, expected_sig):
            return False, "bad_signature"

        return True, "ok"

    def _gc_nonces(self, now: int):
        cutoff = now - self.replay_ttl
        dead = [n for n, t in self.nonce_store.items() if t < cutoff]
        for n in dead:
            self.nonce_store.pop(n, None)

    def api_key_hash(self, renter: str, api_key: str, expected_salt: Optional[bytes]) -> str:
        # PBKDF2-HMAC-SHA256
        if expected_salt is None:
            salt = secrets.token_bytes(16)
        else:
            salt = expected_salt
        dk = hashlib.pbkdf2_hmac("sha256", (renter + ":" + api_key).encode("utf-8"), salt, 200_000)
        return f"pbkdf2${salt.hex()}${dk.hex()}"

    def _verify_api_hash(self, renter: str, api_key: str, expected: str) -> Tuple[bool, str]:
        try:
            parts = expected.split("$")
            if len(parts) != 3 or parts[0] != "pbkdf2":
                return False, "bad_api_hash_format"
            salt = bytes.fromhex(parts[1])
            want = parts[2]
            got = self.api_key_hash(renter, api_key, expected_salt=salt).split("$")[2]
            if hmac.compare_digest(want, got):
                return True, "ok"
            return False, "invalid_api_key"
        except Exception:
            return False, "invalid_api_key"

    def seal(self, plaintext: bytes) -> bytes:
        # encryption optional; if not available, return plaintext
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


# ----------------------------
# Audit log (hash-chained)
# ----------------------------

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
        line = json.dumps(base, ensure_ascii=False, sort_keys=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        self.last_hash = h
        best_effort_chmod_600(self.path)


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
        best_effort_chmod_600(path)


# ----------------------------
# Fleet (tier + SLA-lite)
# ----------------------------

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
        best_effort_chmod_600(self.path)

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


# ----------------------------
# Marketplace: renters, reserved, orderbook, metering, PoS receipts
# ----------------------------

class SecureStateStore:
    """
    Save/load with:
      - optional encryption (Fernet)
      - integrity MAC (HMAC)
    """
    def __init__(self, path: str, sec: SecurityManager, audit: AuditLog):
        self.path = path
        self.sec = sec
        self.audit = audit

    def save(self, obj: Dict[str, Any], tag: str):
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
        best_effort_chmod_600(self.path)
        self.audit.append({"type": "state_save", "tag": tag, "path": self.path, "mac": mac})

    def load(self, default_obj: Dict[str, Any], tag: str) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            self.save(default_obj, tag=tag)
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
                # Tampering detected
                self.audit.append({"type": "tamper_detected", "tag": tag, "path": self.path, "mac": mac, "want": want})
                raise ValueError("STATE_TAMPER_DETECTED")
            obj = json.loads(raw.decode("utf-8"))
            return obj
        except Exception:
            # If state is corrupted, keep safe default but log it
            self.audit.append({"type": "state_load_failed", "tag": tag, "path": self.path})
            return default_obj

class Market:
    """
    State fields:
      renters: renter_id -> {api_hash, created_ts}
      balances: renter_id -> int (earnings)
      credits: renter_id -> int (service credits available)
      reserved: contract_id -> {...}
      orders: order_id -> {...}  (spot bids)
      tier_orders: tier -> [order_id,...]  (index)
      proofs: append-only list of PoS receipt hashes (light)
    """
    def __init__(self, path: str, sec: SecurityManager, audit: AuditLog):
        self.store = SecureStateStore(path, sec, audit)
        self.sec = sec
        self.audit = audit
        self.state = self.store.load({
            "version": 1,
            "renters": {},
            "balances": {},
            "credits": {},
            "reserved": {},
            "orders": {},
            "tier_orders": {t: [] for t in TIERS},
            "nonces": {},   # renter -> {nonce:ts} (optional, we keep global in sec too; this is for persistence)
            "pos_receipts": [],
        }, tag="market")

    def save(self):
        self.store.save(self.state, tag="market")

    # ---- renters/auth ----
    def renter_create(self, renter: str) -> Dict[str, Any]:
        if renter in self.state["renters"]:
            return {"ok": False, "error": "renter_exists"}
        api_key = secrets.token_urlsafe(32)
        api_hash = self.sec.api_key_hash(renter, api_key, expected_salt=None)
        self.state["renters"][renter] = {"api_hash": api_hash, "created_ts": now_ts()}
        self.state["balances"].setdefault(renter, 0)
        self.state["credits"].setdefault(renter, 0)
        self.save()
        self.audit.append({"type": "renter_create", "renter": renter})
        return {"ok": True, "renter": renter, "api_key": api_key}

    def renter_get_api_hash(self, renter: str) -> Optional[str]:
        r = self.state["renters"].get(renter)
        if not r:
            return None
        return str(r.get("api_hash", ""))

    # ---- metering ----
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

    # ---- reserved contracts ----
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
        return out

    # ---- order book ----
    def order_place(self, renter: str, tier: str, bid_bps: int, max_credits: int) -> str:
        oid = h256(jcanon({"r": renter, "tier": tier, "t": now_ts(), "n": os.urandom(8).hex()}))[:16]
        self.state["orders"][oid] = {
            "renter": renter,
            "tier": tier,
            "bid_bps": clamp_int(bid_bps, 0, 10000),     # renters_pool_bps desired (higher is better for renter)
            "max_credits": int(max(0, max_credits)),     # credit budget for metering
            "spent_credits": 0,
            "created_ts": now_ts(),
            "active": True,
        }
        self.state["tier_orders"].setdefault(tier, []).append(oid)
        self.save()
        self.audit.append({"type": "order_place", "renter": renter, "tier": tier, "oid": oid, "bid_bps": bid_bps})
        return oid

    def order_cancel(self, renter: str, order_id: str) -> bool:
        o = self.state["orders"].get(order_id)
        if not o or o.get("renter") != renter:
            return False
        o["active"] = False
        self.save()
        self.audit.append({"type": "order_cancel", "renter": renter, "oid": order_id})
        return True

    def top_spot_orders(self, tier: str, k: int = 5) -> List[Tuple[str, Dict[str, Any]]]:
        ids = self.state["tier_orders"].get(tier, [])
        active = []
        for oid in ids:
            o = self.state["orders"].get(oid)
            if not o or not o.get("active"):
                continue
            # drop if depleted
            if int(o.get("spent_credits", 0)) >= int(o.get("max_credits", 0)):
                continue
            active.append((oid, o))
        # Highest bid_bps wins; tie by earlier created_ts
        active.sort(key=lambda x: (-int(x[1].get("bid_bps", 0)), int(x[1].get("created_ts", 0))))
        return active[:k]

    # ---- payouts ----
    def credit_cost_for_service_unit(self, tier: str) -> int:
        # Higher tiers cost more per service unit (like premium GPU)
        return {"Bronze": 1, "Silver": 2, "Gold": 3, "Platinum": 4}.get(tier, 1)

    def allocate_reward_to_renters(self, renter_alloc: Dict[str, int]):
        for renter, amt in renter_alloc.items():
            self.state["balances"][renter] = int(self.state["balances"].get(renter, 0)) + int(amt)

    # ---- proof-of-service receipts (stub) ----
    def add_pos_receipt(self, receipt: Dict[str, Any]):
        # store only hash to keep light; full receipt is in audit log anyway
        rh = h256(jcanon(receipt))
        self.state["pos_receipts"].append(rh)
        if len(self.state["pos_receipts"]) > 5000:
            self.state["pos_receipts"] = self.state["pos_receipts"][-5000:]


# ----------------------------
# Chain patch: privacy receipts + metered service + mining payout
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
    market: Market,
    privacy_mode: str,  # receipt_only / reveal_to_sender
    audit: AuditLog,
) -> Tuple[bool, str]:
    model = aiguardian.LogisticModel.load(guardian_model_path)
    guardian = aiguardian.Guardian(model, threshold=threshold)

    original_add = aichain.ChainDB.add_tx_to_mempool
    original_build_tpl = aichain.ChainDB.build_block_template
    original_submit = aichain.ChainDB.submit_block

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
            min_fee = bot.policy_min_fee(feats)
            decision, reason = bot.decide(gscore, threshold, min_fee, int(tx.fee))
            votes[decision] += 1
            reasons[reason] = reasons.get(reason, 0) + 1

        decision = max(votes.items(), key=lambda kv: kv[1])[0]
        top_reason = max(reasons.items(), key=lambda kv: kv[1])[0] if reasons else "ok"
        leader = max(committee, key=lambda b: b.score)

        # Metering proof-of-service (service unit): attribute work to renters via orderbook/reserved
        # We simulate that each tx screened consumes 1 service unit from the "winning" renter(s).
        leader_tier = leader.tier
        service_cost = market.credit_cost_for_service_unit(leader_tier)

        winners: List[Tuple[str, Dict[str, Any], str]] = []  # (renter_id, policy, src)
        # reserved has priority
        reserved = market.reserved_active_for_tier(leader_tier)
        if reserved:
            # pick the one with best renters_pool_bps (better deal for renter)
            reserved.sort(key=lambda c: (-int(c.get("renters_pool_bps", 0)), int(c.get("created_ts", 0))))
            winners.append((reserved[0]["renter"], reserved[0], "reserved"))
        else:
            top_orders = market.top_spot_orders(leader_tier, k=1)
            if top_orders:
                oid, o = top_orders[0]
                winners.append((o["renter"], o, "spot_order:" + oid))

        # consume credits (if any winner)
        pos_receipt = {
            "txid": tx.txid(),
            "ts": ts,
            "bot": leader.name,
            "tier": leader_tier,
            "guardian_bucket": ("high" if gscore >= threshold else "low"),
            "service_cost": service_cost,
            "winner": winners[0][0] if winners else None,
            "source": winners[0][2] if winners else None,
        }

        if winners:
            renter_id = winners[0][0]
            if market.consume_credits(renter_id, service_cost):
                # track spending if it was spot order
                src = winners[0][2]
                if src.startswith("spot_order:"):
                    oid = src.split(":", 1)[1]
                    o = market.state["orders"].get(oid)
                    if o:
                        o["spent_credits"] = int(o.get("spent_credits", 0)) + service_cost
                audit.append({"type": "meter_service", **pos_receipt})
                market.add_pos_receipt(pos_receipt)
            else:
                audit.append({"type": "meter_insufficient_credits", **pos_receipt})
        else:
            audit.append({"type": "meter_no_winner", **pos_receipt})

        # Allow/deny/quarantine
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
            market.save()
            return (ok, out)

        # Privacy receipt
        receipt = {
            "status": "quarantined" if decision == "quarantine" else "rejected",
            "txid": tx.txid(),
            "receipt_commitment": None,
            "receipt_proof": None,
            "note": "Privacy receipt (stub). Replace with real ZK proof later.",
        }
        r = make_receipt(tx.txid(), top_reason, bucket_score(float(gscore)))
        receipt["receipt_commitment"] = r["receipt_commitment"]
        receipt["receipt_proof"] = r["receipt_proof"]

        if decision == "quarantine":
            self.quarantine[tx.txid()] = tx.to_dict()  # type: ignore[attr-defined]
            leader.quarantined += 1
            leader.uptime_score = clamp_float(leader.uptime_score - 0.0008, 0.0, 1.0)
        else:
            leader.rejected += 1
            leader.uptime_score = clamp_float(leader.uptime_score - 0.0012, 0.0, 1.0)

        fleet.update_score(leader)
        fleet.save()
        market.save()

        if privacy_mode == "reveal_to_sender":
            receipt["sender_notice"] = {
                "score_bucket": r["score_bucket"],
                "reason_code": r["reason_code"],
                "reveal_secret": r["reveal_secret"],
                "hint": [
                    "Reduce ráfagas (burst).",
                    "Sube el fee si es muy bajo.",
                    "Evita memos largos y demasiados outputs.",
                ]
            }

        return (False, json.dumps(receipt, ensure_ascii=False))

    def fleet_build_template(self: "aichain.ChainDB", miner_addr: str):
        miner = fleet.miner_of_round()
        return original_build_tpl(self, miner.name)

    def wrapped_submit(self: "aichain.ChainDB", blk: "aichain.Block"):
        ok, why = original_submit(self, blk)
        if not ok:
            return (ok, why)

        # identify miner bot
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
            bot.uptime_score = clamp_float(bot.uptime_score + 0.0015, 0.0, 1.0)
            fleet.update_score(bot)
            fleet.save()

            # Determine renters_pool_bps from reserved or top order (per tier)
            tier = bot.tier
            reserved = market.reserved_active_for_tier(tier)
            renters_pool_bps = 0
            payout_mode = "operator_only"

            if reserved:
                reserved.sort(key=lambda c: (-int(c.get("renters_pool_bps", 0)), int(c.get("created_ts", 0))))
                renters_pool_bps = clamp_int(int(reserved[0]["renters_pool_bps"]), 0, 10000)
                payout_mode = "reserved"
                winners = [reserved[0]["renter"]]
            else:
                top_orders = market.top_spot_orders(tier, k=3)
                # We use top 1 for simplicity; extend to top-N split later
                if top_orders:
                    renters_pool_bps = clamp_int(int(top_orders[0][1]["bid_bps"]), 0, 10000)
                    payout_mode = "spot"
                    winners = [top_orders[0][1]["renter"]]
                else:
                    winners = []

            renters_pool = (int(paid) * int(renters_pool_bps)) // 10000
            operator_pool = int(paid) - renters_pool

            # SLA multiplier: renters_pool scaled by uptime_score; remainder back to operator
            renters_pool_sla = int(renters_pool * float(bot.uptime_score))
            operator_pool += (renters_pool - renters_pool_sla)

            renter_alloc: Dict[str, int] = {}
            if winners and renters_pool_sla > 0:
                # If multiple winners, split equally (simple)
                share = renters_pool_sla // len(winners)
                for r in winners:
                    renter_alloc[r] = renter_alloc.get(r, 0) + share
                market.allocate_reward_to_renters(renter_alloc)

            audit.append({
                "type": "block_payout",
                "bot": bot.name,
                "tier": bot.tier,
                "uptime": bot.uptime_score,
                "paid": int(paid),
                "fees": int(fees),
                "subsidy": int(subsidy),
                "payout_mode": payout_mode,
                "renters_pool_bps": int(renters_pool_bps),
                "renters_pool_after_sla": int(renters_pool_sla),
                "operator_pool": int(operator_pool),
                "renter_alloc": renter_alloc,
            })

            market.save()

        return (ok, why)

    aichain.ChainDB.add_tx_to_mempool = guarded_add  # type: ignore[attr-defined]
    aichain.ChainDB.build_block_template = fleet_build_template  # type: ignore[attr-defined]
    aichain.ChainDB.submit_block = wrapped_submit  # type: ignore[attr-defined]
    return True, "orderbook+security patch installed"


# ----------------------------
# Request signing for CLI marketplace actions
# ----------------------------

def make_action_payload(args: argparse.Namespace, extra: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(extra)
    payload["_ts"] = int(args.ts) if getattr(args, "ts", None) is not None else now_ts()
    payload["_nonce"] = getattr(args, "nonce", None) or secrets.token_hex(12)
    return payload

def sign_payload(sec: SecurityManager, renter: str, payload: Dict[str, Any], action: str) -> Dict[str, Any]:
    ts = int(payload["_ts"])
    nonce = str(payload["_nonce"])
    payload2 = dict(payload)
    payload2.pop("_sig", None)
    sig = sec.sign_request(renter, ts, nonce, action, payload2)
    payload2["_sig"] = sig
    return payload2


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

def cmd_renter_create(args, market: Market):
    out = market.renter_create(args.renter)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    if HAVE_FERNET:
        note = "Estado cifrado (Fernet) + HMAC."
    else:
        note = "Estado con HMAC + permisos (sin cifrado; instala 'cryptography' para cifrar)."
    print(json.dumps({"security_note": note}, indent=2, ensure_ascii=False))

def require_auth(args, market: Market, sec: SecurityManager, action: str, payload: Dict[str, Any]) -> Tuple[bool, str]:
    renter = args.renter
    api_key = args.api_key
    api_hash = market.renter_get_api_hash(renter)
    if not api_hash:
        return False, "unknown_renter"
    # payload must include _sig, _ts, _nonce
    ts = int(payload.get("_ts", 0))
    nonce = str(payload.get("_nonce", ""))
    ok, reason = sec.verify_request(renter, api_key, ts, nonce, action, payload, expected_api_hash=api_hash)
    return ok, reason

def cmd_renter_status(args, market: Market, sec: SecurityManager):
    payload = make_action_payload(args, {"action": "renter_status"})
    payload = sign_payload(sec, args.renter, payload, "renter_status")
    ok, reason = require_auth(args, market, sec, "renter_status", payload)
    if not ok:
        print(json.dumps({"ok": False, "error": reason}, indent=2, ensure_ascii=False))
        return
    print(json.dumps({
        "ok": True,
        "renter": args.renter,
        "balance": int(market.state["balances"].get(args.renter, 0)),
        "credits": int(market.state["credits"].get(args.renter, 0)),
        "active_orders": [o for o in market.state["orders"].values() if o.get("renter") == args.renter and o.get("active")],
        "active_reserved": [c for c in market.state["reserved"].values() if c.get("renter") == args.renter and int(c.get("expires_ts", 0)) > now_ts()],
    }, indent=2, ensure_ascii=False))

def cmd_order_place(args, market: Market, sec: SecurityManager, audit: AuditLog):
    if args.tier not in TIERS:
        print(json.dumps({"ok": False, "error": "bad_tier"}, indent=2, ensure_ascii=False))
        return
    payload = make_action_payload(args, {
        "tier": args.tier,
        "bid_bps": int(args.bid_bps),
        "max_credits": int(args.max_credits),
    })
    payload = sign_payload(sec, args.renter, payload, "order_place")
    ok, reason = require_auth(args, market, sec, "order_place", payload)
    if not ok:
        print(json.dumps({"ok": False, "error": reason}, indent=2, ensure_ascii=False))
        return
    oid = market.order_place(args.renter, args.tier, int(args.bid_bps), int(args.max_credits))
    audit.append({"type": "api_order_place", "renter": args.renter, "tier": args.tier, "oid": oid})
    print(json.dumps({"ok": True, "order_id": oid}, indent=2, ensure_ascii=False))

def cmd_order_cancel(args, market: Market, sec: SecurityManager, audit: AuditLog):
    payload = make_action_payload(args, {"order_id": args.order_id})
    payload = sign_payload(sec, args.renter, payload, "order_cancel")
    ok, reason = require_auth(args, market, sec, "order_cancel", payload)
    if not ok:
        print(json.dumps({"ok": False, "error": reason}, indent=2, ensure_ascii=False))
        return
    ok2 = market.order_cancel(args.renter, args.order_id)
    audit.append({"type": "api_order_cancel", "renter": args.renter, "oid": args.order_id, "ok": ok2})
    print(json.dumps({"ok": bool(ok2), "order_id": args.order_id}, indent=2, ensure_ascii=False))

def cmd_order_list(args, market: Market, sec: SecurityManager):
    payload = make_action_payload(args, {"tier": args.tier or ""})
    payload = sign_payload(sec, args.renter, payload, "order_list")
    ok, reason = require_auth(args, market, sec, "order_list", payload)
    if not ok:
        print(json.dumps({"ok": False, "error": reason}, indent=2, ensure_ascii=False))
        return
    orders = []
    for oid, o in market.state["orders"].items():
        if o.get("renter") != args.renter:
            continue
        if args.tier and o.get("tier") != args.tier:
            continue
        orders.append({"order_id": oid, **o})
    orders.sort(key=lambda x: int(x.get("created_ts", 0)), reverse=True)
    print(json.dumps({"ok": True, "orders": orders}, indent=2, ensure_ascii=False))

def cmd_reserved_create(args, market: Market, sec: SecurityManager, audit: AuditLog):
    if args.tier not in TIERS:
        print(json.dumps({"ok": False, "error": "bad_tier"}, indent=2, ensure_ascii=False))
        return
    payload = make_action_payload(args, {
        "tier": args.tier,
        "renters_pool_bps": int(args.renters_pool_bps),
        "duration": int(args.duration),
        "credits": int(args.credits),
    })
    payload = sign_payload(sec, args.renter, payload, "reserved_create")
    ok, reason = require_auth(args, market, sec, "reserved_create", payload)
    if not ok:
        print(json.dumps({"ok": False, "error": reason}, indent=2, ensure_ascii=False))
        return
    cid = market.reserved_create(args.renter, args.tier, int(args.renters_pool_bps), int(args.duration), int(args.credits))
    audit.append({"type": "api_reserved_create", "renter": args.renter, "tier": args.tier, "cid": cid})
    print(json.dumps({"ok": True, "contract_id": cid}, indent=2, ensure_ascii=False))

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
            "accepted": b.accepted,
            "rejected": b.rejected,
            "quarantined": b.quarantined,
        })
    print(json.dumps({"fleet_size": fleet.size, "top": rows}, indent=2, ensure_ascii=False))


# ----------------------------
# Main
# ----------------------------

def main():
    p = argparse.ArgumentParser(prog="aichain_aifleet_orderbook_secure")

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

    p.add_argument("--market-state", default="./market_secure_state.bin")
    p.add_argument("--secret-file", default="./market_secret.key")
    p.add_argument("--audit-log", default="./audit_log.jsonl")
    p.add_argument("--privacy-mode", default="receipt_only", choices=["receipt_only", "reveal_to_sender"])

    # Auth context for protected commands
    p.add_argument("--renter", default="")
    p.add_argument("--api-key", default="")
    p.add_argument("--ts", type=int, default=0)
    p.add_argument("--nonce", default="")

    sp = p.add_subparsers(dest="cmd", required=True)

    sp0 = sp.add_parser("init")
    sp0.set_defaults(func=lambda a, *_: cmd_init(a))

    sp1 = sp.add_parser("send")
    sp1.add_argument("from_addr")
    sp1.add_argument("to_addr")
    sp1.add_argument("amount", type=int)
    sp1.add_argument("--fee", type=int, default=1000)
    sp1.add_argument("--memo", default="")
    sp1.set_defaults(func=lambda a, *_: cmd_send(a))

    sp2 = sp.add_parser("mine")
    sp2.add_argument("any_miner_addr", help="ignored; fleet selects miner bot")
    sp2.set_defaults(func=lambda a, *_: cmd_mine(a))

    sp3 = sp.add_parser("stats")
    sp3.add_argument("--top", type=int, default=20)
    sp3.set_defaults(func=lambda a, f, *_: cmd_stats(a, f))

    # Renter / marketplace
    rc = sp.add_parser("renter-create")
    rc.add_argument("--renter", required=True)
    rc.set_defaults(func=lambda a, _, m, s, ad: cmd_renter_create(a, m))

    rs = sp.add_parser("renter-status")
    rs.add_argument("--renter", required=True)
    rs.add_argument("--api-key", required=True)
    rs.set_defaults(func=lambda a, _, m, s, ad: cmd_renter_status(a, m, s))

    op = sp.add_parser("order-place")
    op.add_argument("--tier", required=True, choices=TIERS)
    op.add_argument("--bid-bps", type=int, required=True, help="desired renters_pool_bps (0..10000)")
    op.add_argument("--max-credits", type=int, default=1000, help="credit budget for metering")
    op.add_argument("--renter", required=True)
    op.add_argument("--api-key", required=True)
    op.set_defaults(func=lambda a, _, m, s, ad: cmd_order_place(a, m, s, ad))

    oc = sp.add_parser("order-cancel")
    oc.add_argument("--order-id", required=True)
    oc.add_argument("--renter", required=True)
    oc.add_argument("--api-key", required=True)
    oc.set_defaults(func=lambda a, _, m, s, ad: cmd_order_cancel(a, m, s, ad))

    ol = sp.add_parser("order-list")
    ol.add_argument("--tier", default="", choices=[""] + TIERS)
    ol.add_argument("--renter", required=True)
    ol.add_argument("--api-key", required=True)
    ol.set_defaults(func=lambda a, _, m, s, ad: cmd_order_list(a, m, s))

    rv = sp.add_parser("reserved-create")
    rv.add_argument("--tier", required=True, choices=TIERS)
    rv.add_argument("--renters-pool-bps", type=int, default=6000)
    rv.add_argument("--duration", type=int, default=3600)
    rv.add_argument("--credits", type=int, default=5000)
    rv.add_argument("--renter", required=True)
    rv.add_argument("--api-key", required=True)
    rv.set_defaults(func=lambda a, _, m, s, ad: cmd_reserved_create(a, m, s, ad))

    args = p.parse_args()

    audit = AuditLog(args.audit_log)
    sec = SecurityManager(args.secret_file)
    fleet = FleetState(args.fleet_state, args.fleet_size, args.fleet_seed, args.committee_size)
    burst = BurstTracker.load(args.burst_state, args.burst_window, args.burst_max)
    market = Market(args.market_state, sec, audit)

    ok, msg = install_patch(
        guardian_model_path=args.guardian_model,
        threshold=args.threshold,
        fleet=fleet,
        burst=burst,
        market=market,
        privacy_mode=args.privacy_mode,
        audit=audit,
    )
    if not ok:
        raise SystemExit(msg)

    # execute command
    args.func(args, fleet, market, sec, audit)

    # persist burst at end
    burst.save(args.burst_state)

if __name__ == "__main__":
    main()
