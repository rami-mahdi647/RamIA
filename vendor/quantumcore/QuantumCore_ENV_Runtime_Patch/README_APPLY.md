# QuantumCore — Parche ENV para Electron (runtime)

## Qué hace
- Añade `.env.example` en la raíz (cópialo/renómbralo a `.env` y rellena valores).
- Modifica `desktop/main.easywallet.full.js` para **cargar .env** en runtime y usar **process.env** como fuente principal.
- Actualiza `desktop/package.json` para **empaquetar** `.env` dentro del instalador (extraResources).

## Cómo aplicar
1) Copia todo el contenido de este ZIP en tu repo **quantumcore**, sobrescribiendo archivos existentes.
2) Duplica `.env.example` → `.env` (en la raíz) y **rellena valores reales** (todas las líneas `CLAVE=valor`).
3) Build local rápido:
   ```bash
   cd web && npm i && npm run build
   cd ../desktop && npm i
   npm run pack:win
   # verás desktop/release/QuantumCore-Setup-*.exe
   ```
4) AppVeyor: el `appveyor.yml` que ya tienes seguirá funcionando;
   el .env se incluirá automáticamente en el instalador gracias a `extraResources`.

## Nota
- Si no quieres empaquetar el `.env`, elimina `extraResources` y define variables del sistema en la máquina final.
