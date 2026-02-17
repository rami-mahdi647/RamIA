# QuantumCore — Easy Wallet Kit

**Objetivo:** simplificar al máximo para usuarios no expertos:
- 1 clic **Crear monedero**
- Frase mnemónica BIP39 (12 palabras)
- Derivación automática multi‑chain (BTC, EVM: ETH/Polygon/BNB, Cosmos; DAG vía Electron)
- **Guardado seguro**: cifrado en navegador (AES‑GCM con PBKDF2) o **Keychain del SO** (Electron con `keytar`)
- Restauración con frase
- Añadir/rotar direcciones por cuenta (m/…/0/i)

## Dónde copiar estos archivos
Colócalos dentro del **frontend React** (`web/`) y de **Electron** (`desktop/`):

```
web/
  src/
    wallet/
      EasyWallet.tsx
    lib/
      hd.ts
      secure.ts
desktop/
  main.easywallet.js   (fusionar con tu main.js si prefieres)
  preload.easywallet.js
```

Luego:
- En React, añade una ruta/tab que importe `<EasyWallet/>` (o sustitúyela por tu `Wallet`).
- En Electron, usa `main.easywallet.js` y `preload.easywallet.js` como base (o copia solo los handlers de IPC a tus `main.js`/`preload.js`).

## Seguridad
- **Navegador**: el seed se cifra con AES‑GCM y una clave derivada (PBKDF2) de una contraseña local del usuario. Se guarda JSON en `localStorage`.
- **Electron**: el seed se guarda en el **Keychain del SO** con `keytar` (no se expone al renderer); se accede vía IPC.

## Derivación por defecto (cuenta 0, índice 0)
- BTC (bech32 p2wpkh): `m/84'/0'/0'/0/0` → `bc1…`
- ETH / Polygon / BNB (EVM): `m/44'/60'/0'/0/0` → `0x…`
- Cosmos (ATOM): `m/44'/118'/0'/0/0` → `cosmos1…`
- DAG: vía `dag4` en **Electron** (IPC), ruta `m/44'/1137'/0'/0/0` (orientativa)

Puedes añadir más índices (0/1/2/…) con el botón “Nueva dirección” en la UI.
