# QuantumCore UI Advanced
Fecha: 2025-08-17

Este paquete añade **todas las pestañas** que aparecen descritas en tu repo (AIAAS, CoinJoin, DAO, Deploy/Interchain, Subscriptions, Vault, Wallet, Market Sentinel, Model Lab, NFTs y Settings) y un **router** por hash.

## Cómo usar
1. Copia el contenido de este ZIP dentro de tu repo (o dentro de `dist/` si compilas).
2. Si usas el kit de escritorio (`/desktop`), sustituye `desktop/main.js` y `desktop/preload.js` por los de `ElectronOverrides/desktop/`.
3. Sirve la carpeta (web) o empaqueta con Electron (AppVeyor) para obtener el `.exe`.

## Datos on-chain (BTC)
- Se consultan endpoints públicos de mempool.space (mempool, fees, blocks, difficulty).
- En escritorio, el preload expone `window.api.fetchJSON` para evitar CORS.
