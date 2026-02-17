cat > run_plus.py << 'PY'
import argparse
import aicore_plus

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--guardian-model", required=True)
    p.add_argument("--fleet-size", type=int, default=800)
    p.add_argument("--committee-size", type=int, default=9)
    p.add_argument("--port", type=int, default=8787)
    args = p.parse_args()

    # Reuse aicore_plus main by emulating its args:
    # easiest: call its run_web_plus directly
    import argparse as ap
    core_args = ap.Namespace(
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
PY
