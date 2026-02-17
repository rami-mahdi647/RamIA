#!/usr/bin/env python3
"""Convenience runner for aicore_plus web mode."""

import argparse

import aicore_plus


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--guardian-model", required=True)
    parser.add_argument("--fleet-size", type=int, default=800)
    parser.add_argument("--committee-size", type=int, default=9)
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    core_args = argparse.Namespace(
        datadir="./aichain_data",
        guardian_model=args.guardian_model,
        threshold=0.7,
        privacy_mode="receipt_only",
        fleet_state="./fleet_state.json",
        fleet_size=args.fleet_size,
        fleet_seed=1337,
        committee_size=args.committee_size,
        burst_state="./burst_state.json",
        burst_window=60,
        burst_max=10,
        market_state="./market_secure_state.bin",
        secret_file="./market_secret.key",
        audit_log="./audit_log.jsonl",
    )
    ctxp = aicore_plus.AppContextPlus(core_args, wallet_file="./wallet.json")
    ui_html = aicore_plus.load_ui_html("./ui_plus.html")
    aicore_plus.run_web_plus(ctxp, ui_html, "127.0.0.1", args.port)


if __name__ == "__main__":
    main()
