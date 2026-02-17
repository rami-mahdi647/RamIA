# QuantumCore — Desktop (Electron) Kit

## ¿Qué es?
Este kit empaqueta tu dApp (carpeta `dist/`, `build/` o estática) en un **instalador de escritorio para Windows (.exe)** usando **Electron + electron-builder**.

## Estructura a añadir al repo
```
/desktop
  package.json
  main.js
  preload.js
  /app           <- aquí copia tu build web (index.html, assets, etc.)
```

## Uso local (dev)
```
cd desktop
npm install
# Copia tu build web a desktop/app/  (o crea un symlink)
npm run start
```
Se abrirá una ventana de escritorio cargando `desktop/app/index.html`.

## Build instalador Windows
```
cd desktop
npm install
npm run pack:win
```
El instalador queda en `desktop/release/QuantumCore-Setup-1.0.0.exe` (o similar).

## Integración con AppVeyor
1) Asegúrate de que tu build web deja `dist/` o `build/` en la raíz del repo.
2) Añade este paso en tu job de Windows **después** del build web:

```powershell
# Copiar la web a desktop/app
$src = 'dist'; if (-not (Test-Path $src)) { if (Test-Path 'build') {{ $src='build' }} else {{ $src='.' }} }
if (Test-Path 'desktop\app') {{ Remove-Item -Recurse -Force 'desktop\app' }}
New-Item -ItemType Directory -Force -Path 'desktop\app' | Out-Null
robocopy $src desktop\app /E /XD node_modules .git | Out-Host

# Construir instalador
Push-Location desktop
cmd /c "npm install --no-fund --no-audit"
cmd /c "npm run pack:win"
Pop-Location

# Renombrar y crear alias "latest"
$ver = $env:APPVEYOR_BUILD_VERSION
$built = Get-ChildItem desktop\release\*.exe | Select-Object -First 1
Copy-Item $built.FullName "QuantumCore-Setup-v$ver.exe" -Force
Copy-Item $built.FullName "QuantumCore-Setup-latest.exe" -Force
```

3) Declara como **artifacts**:
```
- path: QuantumCore-Setup-v$(APPVEYOR_BUILD_VERSION).exe
- path: QuantumCore-Setup-latest.exe
```

## Seguridad
- `nodeIntegration: false`, `contextIsolation: true`, `sandbox: true`.
- Todas las aperturas externas van a navegador (`shell.openExternal`).

## Notas
- Si tu dApp necesita peticiones a red, funcionará igual desde Electron.
- Si usas rutas relativas, asegúrate de que los assets existen dentro de `app/`.
