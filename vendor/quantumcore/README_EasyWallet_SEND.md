# QuantumCore — EasyWallet SEND (EVM/BTC/Cosmos via Electron IPC)

Este paquete añade:
- **Derivación en Electron** (no expone seed al renderer) y **envío** en EVM/BTC/Cosmos.
- **DAG**: info/placeholder por IPC (añadir firma/envío cuando concretemos el flujo).
- UI React con formularios de envío en `EasyWallet`.

## Copia esto en tu repo
- `desktop/main.easywallet.full.js` y `desktop/preload.easywallet.full.js` (o fusiona con tu main/preload).
- `desktop/package.json` (o añade las dependencias indicadas a tu package actual).
- `web/src/wallet/EasyWallet.tsx` (sustituye la anterior).

## AppVeyor (bloque sugerido)
```yaml
install:
  - ps: |
      cd web
      npm ci
      npm run build
      cd ..
      cd desktop
      npm ci
      cd ..

build_script:
  - ps: |
      if (Test-Path 'desktop\app') { Remove-Item -Recurse -Force 'desktop\app' }
      New-Item -ItemType Directory -Force -Path 'desktop\app' | Out-Null
      robocopy web\dist desktop\app /E | Out-Host
      Push-Location desktop
      cmd /c "npm run pack:win"
      $exe = Get-ChildItem release\*.exe | Select-Object -First 1
      Copy-Item $exe.FullName "..\QuantumCore-Setup-latest.exe" -Force
      Pop-Location

artifacts:
  - path: QuantumCore-Setup-latest.exe
```

## Variables
Define en AppVeyor (o en `web/.env`):
- `VITE_ETH_RPC`, `VITE_POLYGON_RPC`, `VITE_BNB_RPC`
- `VITE_COSMOS_RPC`, `VITE_COSMOS_DENOM`
- `VITE_BTC_API` (por defecto mempool.space)

## Avisos
- BTC PSBT simplificada (P2WPKH, inputs largest-first), válida para transferencias sencillas.
- Cosmos: comisiones por defecto `0.025` del denom (ajústalo).
- EVM: monto en ETH/MATIC/BNB según red.
```