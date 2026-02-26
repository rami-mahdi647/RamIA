#!/usr/bin/env bash
set -euo pipefail

# RamIA deploy (infra propia) - "push/pull → relaunch" en Linux.
# - Soporta: Ubuntu/Debian/Kali con systemd (recomendado)
# - Fallback: Termux / distros sin systemd usando tmux
#
# Uso:
#   sudo bash ramia_deploy.sh --repo https://github.com/USER/RamIA.git --branch main --name ramia --port 0
#
# Notas:
# - Este repo (RamIA) es CLI/local-first. Este script levanta un "nodo" tipo miner loop + logs.
# - Para exponer API RPC real (miles de usuarios) necesitarás un servicio HTTP/WebSocket adicional.

REPO_URL=""
BRANCH="main"
APP_NAME="ramia"
INSTALL_DIR="/opt/ramia"
RUN_USER="ramia"
PYTHON_BIN="python3"
USE_OPTIONAL_DEPS="false"
PORT="0"  # reservado por si luego añades API

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO_URL="$2"; shift 2;;
    --branch) BRANCH="$2"; shift 2;;
    --name) APP_NAME="$2"; shift 2;;
    --dir) INSTALL_DIR="$2"; shift 2;;
    --user) RUN_USER="$2"; shift 2;;
    --python) PYTHON_BIN="$2"; shift 2;;
    --optional-deps) USE_OPTIONAL_DEPS="true"; shift 1;;
    --port) PORT="$2"; shift 2;;
    -h|--help)
      sed -n '1,120p' "$0"; exit 0;;
    *) echo "Arg desconocido: $1"; exit 2;;
  esac
done

if [[ -z "$REPO_URL" ]]; then
  echo "ERROR: Falta --repo <URL del repo GitHub>" >&2
  exit 2
fi

is_root() { [[ "$(id -u)" -eq 0 ]]; }
have_cmd() { command -v "$1" >/dev/null 2>&1; }
have_systemd() { have_cmd systemctl && systemctl --version >/dev/null 2>&1; }

log() { echo -e "\n[ramia-deploy] $*"; }

ensure_packages_debian() {
  log "Instalando dependencias base (git, python3, pip, tmux)..."
  apt-get update -y
  apt-get install -y git "$PYTHON_BIN" python3-pip tmux ca-certificates curl
}

ensure_user_and_dirs() {
  log "Creando usuario y directorios…"
  if ! id "$RUN_USER" >/dev/null 2>&1; then
    useradd -m -s /bin/bash "$RUN_USER"
  fi
  mkdir -p "$INSTALL_DIR"
  chown -R "$RUN_USER":"$RUN_USER" "$INSTALL_DIR"
}

clone_or_update_repo() {
  log "Clonando/actualizando repo…"
  if [[ ! -d "$INSTALL_DIR/.git" ]]; then
    sudo -u "$RUN_USER" git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$INSTALL_DIR"
  else
    sudo -u "$RUN_USER" bash -lc "cd '$INSTALL_DIR' && git fetch --all --prune && git checkout '$BRANCH' && git pull --ff-only"
  fi
}

setup_venv() {
  log "Creando venv…"
  sudo -u "$RUN_USER" bash -lc "cd '$INSTALL_DIR' && $PYTHON_BIN -m venv .venv"

  log "Actualizando pip…"
  sudo -u "$RUN_USER" bash -lc "cd '$INSTALL_DIR' && . .venv/bin/activate && python -m pip install --upgrade pip"

  if [[ "$USE_OPTIONAL_DEPS" == "true" ]]; then
    log "Instalando deps opcionales (cryptography, argon2-cffi, flask, stripe)…"
    sudo -u "$RUN_USER" bash -lc "cd '$INSTALL_DIR' && . .venv/bin/activate && pip install cryptography argon2-cffi flask stripe"
  else
    log "Deps opcionales: omitidas (puedes activar con --optional-deps)."
  fi
}

init_chain_if_needed() {
  log "Inicializando chain si hace falta…"
  # Si no existe state.json, inicializa.
  if [[ ! -f "$INSTALL_DIR/aichain_data/state.json" ]]; then
    sudo -u "$RUN_USER" bash -lc "cd '$INSTALL_DIR' && . .venv/bin/activate && python ramia_node.py init"
  else
    log "state.json ya existe: no reinicio genesis/estado."
  fi
}

write_systemd_units() {
  local svc="${APP_NAME}.service"
  local upd_svc="${APP_NAME}-update.service"
  local upd_timer="${APP_NAME}-update.timer"

  log "Creando servicios systemd ($svc + auto-update)…"

  cat > "/etc/systemd/system/$svc" <<EOF
[Unit]
Description=RamIA node miner loop ($APP_NAME)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=/bin/bash -lc 'cd "$INSTALL_DIR" && . .venv/bin/activate && python ramia_node.py mine miner_main --loop --sleep 2 >> logs/miner.log 2>&1'
Restart=always
RestartSec=2

# Endurecimiento básico
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=$INSTALL_DIR

[Install]
WantedBy=multi-user.target
EOF

  # Servicio de update: git pull + restart si hay cambios
  cat > "/etc/systemd/system/$upd_svc" <<EOF
[Unit]
Description=RamIA auto-update from GitHub ($APP_NAME)

[Service]
Type=oneshot
User=$RUN_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=/bin/bash -lc 'cd "$INSTALL_DIR" && BEFORE=$(git rev-parse HEAD) && git fetch --all --prune && git checkout "$BRANCH" && git pull --ff-only && AFTER=$(git rev-parse HEAD) && if [ "$BEFORE" != "$AFTER" ]; then echo "Updated: $BEFORE -> $AFTER"; systemctl restart "$svc"; fi'
EOF

  # Timer: cada 2 minutos (ajusta a gusto)
  cat > "/etc/systemd/system/$upd_timer" <<EOF
[Unit]
Description=Run RamIA auto-update periodically ($APP_NAME)

[Timer]
OnBootSec=90
OnUnitActiveSec=120
Unit=$upd_svc

[Install]
WantedBy=timers.target
EOF

  systemctl daemon-reload
  systemctl enable --now "$svc"
  systemctl enable --now "$upd_timer"

  log "Listo: servicio activo. Ver logs: journalctl -u $svc -f"
}

tmux_fallback() {
  log "systemd no disponible → usando tmux (fallback)."
  log "Creando script run y updater…"

  sudo -u "$RUN_USER" bash -lc "cat > '$INSTALL_DIR/run_tmux_node.sh' <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd '$INSTALL_DIR'
. .venv/bin/activate
mkdir -p logs
# Sesión tmux persistente
SESSION='${APP_NAME}'
if tmux has-session -t \"$SESSION\" 2>/dev/null; then
  echo 'tmux session already running'
  exit 0
fi
# Mine loop
tmux new-session -d -s \"$SESSION\" \"python ramia_node.py mine miner_main --loop --sleep 2 >> logs/miner.log 2>&1\"

echo "Started tmux session: $SESSION"
EOF
chmod +x '$INSTALL_DIR/run_tmux_node.sh'"

  sudo -u "$RUN_USER" bash -lc "cat > '$INSTALL_DIR/update_and_restart.sh' <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd '$INSTALL_DIR'
BEFORE=$(git rev-parse HEAD)
git fetch --all --prune
git checkout '$BRANCH'
git pull --ff-only
AFTER=$(git rev-parse HEAD)
if [ "$BEFORE" != "$AFTER" ]; then
  echo "Updated: $BEFORE -> $AFTER"
  SESSION='${APP_NAME}'
  if tmux has-session -t \"$SESSION\" 2>/dev/null; then
    tmux kill-session -t \"$SESSION\" || true
  fi
  ./run_tmux_node.sh
fi
EOF
chmod +x '$INSTALL_DIR/update_and_restart.sh'"

  log "Inicia el nodo: sudo -u $RUN_USER $INSTALL_DIR/run_tmux_node.sh"
  log "Para auto-update, puedes usar cron (cada 2 min):"
  echo "*/2 * * * * cd $INSTALL_DIR && ./update_and_restart.sh >> $INSTALL_DIR/logs/updater.log 2>&1" | sed 's/^/[CRON] /'
}

main() {
  if ! is_root; then
    echo "ERROR: Ejecuta como root (usa sudo)" >&2
    exit 1
  fi

  if have_cmd apt-get; then
    ensure_packages_debian
  else
    log "No detecté apt-get. Instala manualmente: git, python3, pip, tmux."
  fi

  ensure_user_and_dirs
  clone_or_update_repo
  setup_venv
  init_chain_if_needed

  if have_systemd; then
    write_systemd_units
  else
    tmux_fallback
  fi

  log "Hecho. Directorio: $INSTALL_DIR"
  log "Tip: para ver estado del chain: sudo -u $RUN_USER bash -lc 'cd $INSTALL_DIR && . .venv/bin/activate && python ramia_node.py chain --n 10'"
}

main
