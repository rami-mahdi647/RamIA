#!/usr/bin/env bash
set -euo pipefail
REQUIRED=( VITE_ETH_RPC VITE_POLYGON_RPC VITE_BNB_RPC VITE_COSMOS_RPC VITE_COSMOS_DENOM VITE_BTC_API VITE_DAG_NODE )
MISSING=()
for V in "${REQUIRED[@]}"; do
  if [ -z "${!V:-}" ]; then MISSING+=("$V"); fi
done
if [ "${#MISSING[@]}" -gt 0 ]; then
  echo "Faltan variables: ${MISSING[*]}"
  exit 1
fi
echo "Preflight OK"
