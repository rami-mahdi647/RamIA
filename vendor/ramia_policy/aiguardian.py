#!/usr/bin/env python3
# AIGuardian: transaction risk/spam filter nucleus.
# Pure-python logistic regression + feature extraction + CSV training pipeline.
# Not legal advice. Not AML compliance. Just a clean hook for defensive screening.

import argparse
import csv
import json
import math
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


# ----------------------------
# Feature extraction
# ----------------------------

@dataclass
class TxFeatures:
    # Keep it cheap. Add graph features later (neighbors, cycles, bursts, etc).
    amount: float
    fee: float
    outputs: int
    memo_len: int
    addr_entropy: float
    burst_score: float       # requires local history in prod; here can be precomputed in dataset
    hour: int                # 0..23

    def to_vector(self) -> List[float]:
        return [
            self.amount,
            self.fee,
            float(self.outputs),
            float(self.memo_len),
            self.addr_entropy,
            self.burst_score,
            float(self.hour),
            1.0,  # bias term
        ]


def shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    freq: Dict[str, int] = {}
    for ch in s:
        freq[ch] = freq.get(ch, 0) + 1
    n = float(len(s))
    ent = 0.0
    for c in freq.values():
        p = float(c) / n
        ent -= p * math.log(p + 1e-12, 2)
    return ent


def extract_features(tx: Dict[str, Any]) -> TxFeatures:
    # Expected tx dict shape:
    # {
    #   "amount": 12345, "fee": 12, "outputs": 2, "memo": "...",
    #   "to_addr": "xyz", "burst_score": 0.0, "timestamp": 1700000000
    # }
    amount = float(tx.get("amount", 0.0))
    fee = float(tx.get("fee", 0.0))
    outputs = int(tx.get("outputs", 1))
    memo = str(tx.get("memo", ""))
    to_addr = str(tx.get("to_addr", ""))
    burst_score = float(tx.get("burst_score", 0.0))
    ts = int(tx.get("timestamp", 0))
    hour = (ts // 3600) % 24 if ts > 0 else 0
    addr_entropy = shannon_entropy(to_addr)
    return TxFeatures(
        amount=amount,
        fee=fee,
        outputs=outputs,
        memo_len=len(memo),
        addr_entropy=addr_entropy,
        burst_score=burst_score,
        hour=hour,
    )


# ----------------------------
# Model: logistic regression (SGD)
# ----------------------------

class LogisticModel:
    def __init__(self, dim: int):
        self.w = [0.0] * dim

    def _sigmoid(self, z: float) -> float:
        if z >= 0:
            ez = math.exp(-z)
            return 1.0 / (1.0 + ez)
        ez = math.exp(z)
        return ez / (1.0 + ez)

    def predict_proba(self, x: List[float]) -> float:
        z = 0.0
        for wi, xi in zip(self.w, x):
            z += wi * xi
        return self._sigmoid(z)

    def update(self, x: List[float], y: int, lr: float, l2: float):
        p = self.predict_proba(x)
        # gradient of logloss
        err = (p - float(y))
        for i in range(len(self.w)):
            self.w[i] -= lr * (err * x[i] + l2 * self.w[i])

    def save(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"w": self.w}, indent=2))

    @staticmethod
    def load(path: str) -> "LogisticModel":
        with open(path, "r", encoding="utf-8") as f:
            obj = json.loads(f.read())
        m = LogisticModel(dim=len(obj["w"]))
        m.w = [float(v) for v in obj["w"]]
        return m


# ----------------------------
# Guardian: policy wrapper
# ----------------------------

class Guardian:
    def __init__(self, model: LogisticModel, threshold: float):
        self.model = model
        self.threshold = threshold

    def score(self, tx: Dict[str, Any]) -> float:
        feats = extract_features(tx).to_vector()
        return self.model.predict_proba(feats)

    def allow(self, tx: Dict[str, Any]) -> Tuple[bool, float]:
        s = self.score(tx)
        return (s < self.threshold), s


# ----------------------------
# Dataset IO
# ----------------------------

def read_csv_dataset(path: str) -> List[Tuple[List[float], int]]:
    """
    CSV columns expected (minimum):
      amount,fee,outputs,memo,to_addr,burst_score,timestamp,label
    label: 0=clean, 1=spam/abuse (or "high-risk" per your chosen taxonomy)
    """
    rows: List[Tuple[List[float], int]] = []
    with open(path, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            tx = {
                "amount": row.get("amount", "0"),
                "fee": row.get("fee", "0"),
                "outputs": row.get("outputs", "1"),
                "memo": row.get("memo", ""),
                "to_addr": row.get("to_addr", ""),
                "burst_score": row.get("burst_score", "0"),
                "timestamp": row.get("timestamp", "0"),
            }
            y = int(row.get("label", "0"))
            x = extract_features(tx).to_vector()
            rows.append((x, y))
    return rows


def train(model: LogisticModel, data: List[Tuple[List[float], int]], epochs: int, lr: float, l2: float) -> Dict[str, float]:
    # simple shuffle-less loop (deterministic); swap in a proper trainer later
    n = len(data)
    if n == 0:
        return {"n": 0, "loss": 0.0, "acc": 0.0}

    for _ in range(epochs):
        for x, y in data:
            model.update(x, y, lr=lr, l2=l2)

    # evaluate
    loss = 0.0
    correct = 0
    for x, y in data:
        p = model.predict_proba(x)
        # logloss
        p = min(1.0 - 1e-9, max(1e-9, p))
        loss += -(y * math.log(p) + (1 - y) * math.log(1 - p))
        pred = 1 if p >= 0.5 else 0
        if pred == y:
            correct += 1
    return {"n": float(n), "loss": float(loss / n), "acc": float(correct / n)}


# ----------------------------
# CLI
# ----------------------------

def cmd_train(args):
    data = read_csv_dataset(args.csv)
    # dim inferred from feature vector
    dim = len(data[0][0]) if data else 8
    model = LogisticModel(dim=dim)
    metrics = train(model, data, epochs=args.epochs, lr=args.lr, l2=args.l2)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    model.save(args.out)

    print("ok trained")
    print("model", args.out)
    print("n", int(metrics["n"]))
    print("loss", metrics["loss"])
    print("acc", metrics["acc"])

def cmd_score(args):
    model = LogisticModel.load(args.model)
    g = Guardian(model, threshold=args.threshold)

    # tx json from file or stdin
    if args.tx == "-":
        tx = json.loads(input().strip())
    else:
        with open(args.tx, "r", encoding="utf-8") as f:
            tx = json.loads(f.read())

    allow, s = g.allow(tx)
    print(json.dumps({"allow": bool(allow), "score": float(s), "threshold": float(args.threshold)}, indent=2))

def cmd_example(args):
    example = {
        "amount": 250000,
        "fee": 120,
        "outputs": 2,
        "memo": "payment",
        "to_addr": "a1b2c3d4e5f6",
        "burst_score": 0.0,
        "timestamp": 1700000000,
    }
    print(json.dumps(example, indent=2))

def main():
    p = argparse.ArgumentParser(prog="aiguardian")
    sp = p.add_subparsers(dest="cmd", required=True)

    t = sp.add_parser("train")
    t.add_argument("--csv", required=True, help="dataset CSV with label column")
    t.add_argument("--out", default="./guardian_model.json")
    t.add_argument("--epochs", type=int, default=5)
    t.add_argument("--lr", type=float, default=1e-4)
    t.add_argument("--l2", type=float, default=1e-6)
    t.set_defaults(func=cmd_train)

    s = sp.add_parser("score")
    s.add_argument("--model", required=True)
    s.add_argument("--tx", required=True, help="tx json path, or '-' for stdin")
    s.add_argument("--threshold", type=float, default=0.7)
    s.set_defaults(func=cmd_score)

    e = sp.add_parser("example-tx")
    e.set_defaults(func=cmd_example)

    args = p.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
