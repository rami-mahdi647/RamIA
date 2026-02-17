# QuantumCore — Production Checklist (2025-08-17)

## 1) Estructura recomendada
```
quantumcore/
├─ web/                 # React + Vite + Tailwind (frontend)
│  ├─ src/
│  └─ package.json
├─ desktop/             # Electron + electron-builder
│  ├─ main.easywallet.full.js
│  ├─ preload.easywallet.full.js
│  ├─ package.json
│  └─ app/             # (se genera) contiene el build de web
├─ contracts/           # (si usas hardhat/foundry)
├─ backend/             # (si tienes API propia)
├─ scripts/             # scripts utilitarios (deploy, healthchecks, etc.)
├─ test/
├─ appveyor.yml         # CI (Windows .exe + opcional Linux AppImage)
└─ README.md
```

## 2) Variables de entorno
Define en **AppVeyor → Settings → Environment** (ocultas/secure):
- `VITE_ETH_RPC`, `VITE_POLYGON_RPC`, `VITE_BNB_RPC`
- `VITE_COSMOS_RPC`, `VITE_COSMOS_DENOM`
- `VITE_BTC_API`, `VITE_DAG_NODE`

*(Para uso local: `web/.env` con los mismos nombres — no subirlo a Git)*
*El `appveyor.yml` solo contiene `secure: REPLACE_IN_APPVEYOR_UI`; debes ingresar los valores reales en la UI de AppVeyor.*

## 3) Build local (prueba rápida)
```bash
# Frontend
cd web && npm i && npm run build

# Copiar al contenedor Electron
rm -rf ../desktop/app && mkdir -p ../desktop/app
cp -r dist/* ../desktop/app/

# Desktop
cd ../desktop && npm i && npm run pack:win
# Resultado: desktop/release/QuantumCore-Setup-*.exe
```

## 4) Seguridad
- **Seeds/keys** solo en **Electron** (keychain) vía IPC `vault:*`.
- **Frontend** no maneja claves privadas, solo direcciones/lecturas.
- Nunca hardcodear API keys; usar `.env` local o **secrets** de AppVeyor.

## 5) QA rápido antes de publicar
- [ ] Web carga todas las vistas (Dashboard/Wallet/DAO/Interchain/Market/Models/Subscriptions/NFTs/Settings).
- [ ] EasyWallet: crear + restaurar + desbloquear con contraseña local.
- [ ] Derivación multi‑chain correcta (BTC/EVM/Cosmos/DAG placeholder).
- [ ] Envíos: EVM (tx hash visible), BTC (txid), Cosmos (ok/txhash).
- [ ] Artefacto `.exe` generado y descargable como artifact.
- [ ] Sin warnings bloqueantes en AppVeyor; `node -v` es 20.x.

## 6) Publicación
- Usa la pestaña **Artifacts** de AppVeyor para obtener el `.exe` público.
- Si quieres “release tipo Bitcoin Core”, crea **Releases** y sube el `.exe` y checksums.
