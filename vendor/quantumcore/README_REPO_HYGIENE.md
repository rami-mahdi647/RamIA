# QuantumCore — Repo Hygiene Patch (2025-08-17)

Este parche:
- Añade **.gitignore** (no subir `web/dist`, `desktop/release`, `desktop/app`, `.env`).
- Añade **.gitattributes** para que GitHub cuente TS/JS y **ignore bundles** generados.
- Scripts para mover HTML sueltos de la raíz a **legacy/**.

## Cómo aplicarlo
1. Copia estos archivos a la **raíz** del repo `quantumcore` y confirma reemplazar si lo pide:
   - `.gitignore`
   - `.gitattributes`
   - `scripts/repo_cleanup.ps1` y/o `scripts/repo_cleanup.sh`

2. Mueve los prototipos HTML a `legacy/`:
   - **Windows (PowerShell):**
     ```powershell
     ./scripts/repo_cleanup.ps1
     ```
   - **macOS/Linux:**
     ```bash
     bash scripts/repo_cleanup.sh
     ```

3. Haz commit y push:
   ```bash
   git add .gitattributes .gitignore legacy/ scripts/
   git commit -m "chore(repo): hygiene (ignore builds, mark generated, move legacy html)"
   git push
   ```

> Tras el push, GitHub recalculará el lenguaje y dejará de mostrar ~99% HTML.
