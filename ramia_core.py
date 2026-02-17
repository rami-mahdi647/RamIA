#!/usr/bin/env python3
import argparse
import os
import sys

def parse_conf(path: str):
    cfg = {}
    if not os.path.exists(path):
        return cfg
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    return cfg

def as_int(cfg, k, default):
    try: return int(cfg.get(k, default))
    except: return default

def as_float(cfg, k, default):
    try: return float(cfg.get(k, default))
    except: return default

def as_bool(cfg, k, default):
    v = str(cfg.get(k, "1" if default else "0")).lower()
    return v in ("1","true","yes","on")

def main():
    p = argparse.ArgumentParser(prog="ramia-core")
    p.add_argument("--conf", default="./ramia.conf", help="path to config file")
    p.add_argument("--guardian-model", default=None)
    p.add_argument("--datadir", default=None)
    p.add_argument("--web", action="store_true")
    p.add_argument("--no-web", action="store_true")
    p.add_argument("--web-port", type=int, default=None)
    p.add_argument("--web-host", default=None)
    args = p.parse_args()

    cfg = parse_conf(args.conf)

    guardian_model = args.guardian_model or cfg.get("guardian_model") or "./guardian_model.json"
    datadir = args.datadir or cfg.get("datadir") or "./aichain_data"
    threshold = as_float(cfg, "threshold", 0.70)
    privacy_mode = cfg.get("privacy_mode", "receipt_only")

    fleet_size = as_int(cfg, "fleet_size", 2000)
    committee_size = as_int(cfg, "committee_size", 11)
    fleet_seed = as_int(cfg, "fleet_seed", 1337)

    wallet_file = cfg.get("wallet_file", "./wallet.json")
    ui_file = cfg.get("ui_file", "./coreui/ui_plus.html")

    web_enabled = as_bool(cfg, "web", True)
    if args.web: web_enabled = True
    if args.no_web: web_enabled = False
    web_host = args.web_host or cfg.get("web_host", "127.0.0.1")
    web_port = args.web_port or as_int(cfg, "web_port", 8787)

    # Import here to fail fast if missing
    import aicore_plus

    core_args = argparse.Namespace(
        datadir=datadir,
        guardian_model=guardian_model,
        threshold=threshold,
        privacy_mode=privacy_mode,

        fleet_state=cfg.get("fleet_state","./fleet_state.json"),
        fleet_size=fleet_size,
        fleet_seed=fleet_seed,
        committee_size=committee_size,

        burst_state=cfg.get("burst_state","./burst_state.json"),
        burst_window=as_int(cfg,"burst_window",60),
        burst_max=as_int(cfg,"burst_max",10),

        market_state=cfg.get("market_state","./market_secure_state.bin"),
        secret_file=cfg.get("secret_file","./market_secret.key"),
        audit_log=cfg.get("audit_log","./audit_log.jsonl"),
    )

    ctxp = aicore_plus.AppContextPlus(core_args, wallet_file=wallet_file)

    # UI file
    if not os.path.exists(ui_file):
        print(f"[fatal] ui file not found: {ui_file}", file=sys.stderr)
        print("Hint: put ui_plus.html in ./coreui/ui_plus.html or set ui_file= in ramia.conf", file=sys.stderr)
        sys.exit(2)

    html = aicore_plus.load_ui_html(ui_file)

    if not web_enabled:
        print("[node] web disabled by config.")
        print("[node] This runner currently focuses on Web UI. Use CLI commands via aicore/aicore_plus.")
        sys.exit(0)

    print(f"[ramia-core] datadir={datadir}")
    print(f"[ramia-core] guardian_model={guardian_model}")
    print(f"[ramia-core] web=http://{web_host}:{web_port}")
    aicore_plus.run_web_plus(ctxp, html, web_host, web_port)

if __name__ == "__main__":
    main()
