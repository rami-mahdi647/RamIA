# RamIA — Developer Runtime Guide

This repository README is for technical users who want to run RamIA from the terminal on local machines (Linux, Ubuntu, macOS, and Windows).

> Focus: running the software stack locally (node process + local web/API surface). This is not a marketing or Netlify-first guide.

## What this repository contains

- `ramia_core_plus.py`: main local runtime entrypoint (web server + local API routes).
- `aicore_plus.py`: local application context and handler stack used by `ramia_core_plus.py`.
- `aichain.py`, `ramia_core.py`, `ramia_core_v1.py`: chain/runtime variants and related CLI flows.
- `ui_plus.html`: local UI served by the runtime.
- `site/`: static web assets for hosted/browser-facing frontend.

## Prerequisites

- Git
- Python 3.10+
- Node.js 18+ and npm (required for JS dependencies used in this repo)

Check your environment:

```bash
git --version
python3 --version
node --version
npm --version
```

## Clone and install
# RamIA (Technical README)

Repositorio técnico de **RamIA** para ejecutar nodo local, motor de tokenomics y pruebas de integración de pagos (Stripe + funciones serverless).

> Este README está orientado a personas técnicas que trabajan desde terminal (CLI), no al flujo básico de la web pública.

## 1) Arquitectura del repositorio

- **Núcleo local (Python)**
  - `aichain.py`, `aicore_plus.py`, `ramia_core.py`, `ramia_core_plus.py`, `ramia_core_v1.py`
  - Ejecutan nodo local, estado, web local y endpoint de canje de grants.
- **Tokenomics (Python)**
  - `tokenomics_v1.py`
  - Incluye validación determinista con `--self-test`.
- **Puente Stripe (Python)**
  - `stripe_bridge.py`
  - Verificación/canje local de tokens de grant.
- **Funciones serverless (Node.js)**
  - `netlify/functions/*.js`
  - Checkout + webhook + obtención de grant token.
- **Frontend estático (PWA)**
  - `site/*`
  - UI estática desplegable en Netlify u otro hosting estático.

---

## 2) Requisitos

### Requisitos generales

- `git`
- `python3` (recomendado 3.10+)
- `node` + `npm` (recomendado Node 18+)

### Verificación rápida

```bash
git --version
python3 --version
node --version
npm --version
```

---

## 3) Clonar e instalar dependencias

```bash
git clone <URL_DEL_REPO>
cd RamIA
npm install
```

> `npm install` instala dependencias usadas por funciones serverless (`stripe`, `@netlify/blobs`).

---

## 4) Ejecución por sistema operativo

## Linux (genérico)

### Instalar runtime (Debian/Ubuntu)

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip nodejs npm
```

### Ejecutar nodo local

```bash
git clone <REPO_URL>
cd RamIA
npm install
```

---

## Platform setup

### Linux (generic)

### Ejecutar self-test de tokenomics
ain

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip nodejs npm
```

Then run:

```bash
git clone <REPO_URL>
cd RamIA
npm install
python3 ramia_core_plus.py --guardian-model ./guardian_model.json --web --web-host 127.0.0.1 --web-port 8787
```

### Ubuntu (recommended flow)

1) Install dependencies:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl python3 python3-venv python3-pip nodejs npm
```

2) Clone and install:

---

## Ubuntu (paso a paso recomendado)

### 1. Dependencias

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl python3 python3-venv python3-pip nodejs npm
```

### 2. Clonar e instalar

```bash
git clone <URL_DEL_REPO>
cd RamIA
npm install
```

### 3. Arrancar nodo local

```bash
python3 ramia_core_plus.py --guardian-model ./guardian_model.json --web --web-host 127.0.0.1 --web-port 8787
```

### 4. Validar estado (tokenomics + minería v1)

```bash
python3 tokenomics_v1.py --self-test
python3 ramia_core_v1.py --datadir ./aichain_data_v1 mine miner_demo
python3 ramia_core_v1.py --datadir ./aichain_data_v1 status
```

---

## macOS

### Instalar herramientas base (Homebrew)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python node git
```

### Ejecutar proyecto

```bash
git clone <URL_DEL_REPO>
cd RamIA
npm install
python3 ramia_core_plus.py --guardian-model ./guardian_model.json --web
```

### Tests rápidos

```bash
python3 tokenomics_v1.py --self-test
```

```bash
git clone <REPO_URL>
cd RamIA
npm install
```

3) Start local runtime:

```bash
python3 ramia_core_plus.py \
  --guardian-model ./guardian_model.json \
  --web \
  --web-host 127.0.0.1 \
  --web-port 8787
```

### macOS

Install tools (Homebrew):

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install git python node
```

Run:

```bash
git clone <REPO_URL>
cd RamIA
npm install
python3 ramia_core_plus.py --guardian-model ./guardian_model.json --web
```

### Windows (PowerShell)

Install first:
- Git for Windows
- Python 3 (enable **Add python.exe to PATH**)
- Node.js LTS

Then run:

```powershell
git clone <REPO_URL>
cd RamIA
npm install
py -3 ramia_core_plus.py --guardian-model .\guardian_model.json --web --web-host 127.0.0.1 --web-port 8787
```

### Windows option: WSL2 + Ubuntu

If you prefer a Linux-like workflow on Windows, use WSL2 Ubuntu and follow the Ubuntu section above.

---

## Running the software

## Main runtime command

```bash
python3 ramia_core_plus.py --guardian-model ./guardian_model.json --web
```

Useful flags:

- `--datadir <path>`: chain/state directory.
- `--web`: force-enable local web server.
- `--no-web`: disable local web server.
- `--web-host <host>`: bind host (default from config, commonly `127.0.0.1`).
- `--web-port <port>`: bind port (default commonly `8787`).
- `--conf <path>`: use custom runtime config file.

## Local endpoint contract

When the runtime is started with web enabled, it exposes:

- `POST /api/redeem_grant`

Request body:
=======
## Windows (PowerShell)

### Opción A (nativa)

1. Instala:
   - Git for Windows
   - Python 3 (marcar "Add python.exe to PATH")
   - Node.js LTS

2. En PowerShell:

```powershell
git clone <URL_DEL_REPO>
cd RamIA
npm install
py -3 ramia_core_plus.py --guardian-model .\guardian_model.json --web
```

3. Self-test:

```powershell
py -3 tokenomics_v1.py --self-test
```

### Opción B (recomendada para entorno Linux en Windows): WSL2 + Ubuntu

Usa la sección de **Ubuntu** de este README.

---

## 5) Ejecución de funciones serverless (modo local rápido)

Prueba de contrato básico de la función `create_checkout_session` sin levantar Netlify completo:

```bash
node -e "const fn=require('./netlify/functions/create_checkout_session'); fn.handler({httpMethod:'POST',body:JSON.stringify({renter:'demo',bots_count:2})}).then(x=>console.log(x.statusCode));"
```

> Para crear sesiones reales en Stripe, define variables de entorno válidas y salida a Internet.

---

## 6) Variables de entorno (Stripe / serverless)

Variables usadas por funciones:

- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `SITE_URL`
- `STRIPE_GRANT_SECRET` (opcional, recomendado)
- `BOT_RENT_PRICE_USD` (opcional; default `1000`)
- `GRANT_FETCH_TTL_SECONDS` (opcional; default `600`)

Ejemplo Linux/macOS:

```bash
export STRIPE_SECRET_KEY='sk_live_or_test_xxx'
export STRIPE_WEBHOOK_SECRET='whsec_xxx'
export SITE_URL='https://tu-dominio-o-netlify.app'
```

Ejemplo PowerShell:

```powershell
$env:STRIPE_SECRET_KEY='sk_live_or_test_xxx'
$env:STRIPE_WEBHOOK_SECRET='whsec_xxx'
$env:SITE_URL='https://tu-dominio-o-netlify.app'
```

---

## 7) API local de canje de grant

Endpoint expuesto por `ramia_core_plus.py`:

- `POST /api/redeem_grant`

Payload:

```json
{
  "renter": "demo",
  "token": "<grant_token>"
}
```

Example request:

Ejemplo:

```bash
curl -X POST http://127.0.0.1:8787/api/redeem_grant \
  -H 'Content-Type: application/json' \
  -d '{"renter":"demo","token":"<grant_token_here>"}'
```

---

## Minimal terminal verification

Run these after setup:

```bash
python3 ramia_core_plus.py --help
python3 ramia_core.py --help
python3 ramia_core_v1.py --help
```

If those CLI help commands work, your Python runtime and script entrypoints are correctly discovered.

---

## Troubleshooting

- `python3: command not found`
  - Python is not installed or not in PATH.
- `py : The term 'py' is not recognized` (Windows)
  - Reinstall Python and ensure launcher/PATH integration is enabled.
- `Error: Cannot find module ...` (Node)
  - Run `npm install` in repo root.
- Port already in use (`8787`)
  - Start with `--web-port 8788` (or any free port).
- Runtime fails to boot due to missing files
  - Confirm `guardian_model.json` and `ui_plus.html` exist at expected paths.

---

## Recommended developer workflow

1. Install dependencies and clone the repo.
2. Validate CLI entrypoints with `--help`.
3. Start `ramia_core_plus.py` with explicit host/port.
4. Hit local endpoints using `curl`.
5. Iterate with custom `--datadir` and `--conf` profiles.

## 8) Flujo de trabajo técnico recomendado

1. Ejecutar pruebas deterministas de tokenomics.
2. Validar nodo local (`ramia_core_plus.py`).
3. Probar endpoint local `/api/redeem_grant` con token de prueba.
4. Probar funciones serverless en local (contrato) o en entorno Netlify.
5. Integrar webhook Stripe en entorno de staging antes de producción.

---

## 9) Troubleshooting

- **`python3: command not found`**
  - Instalar Python y/o ajustar PATH.
- **`Module not found` en Node**
  - Ejecutar `npm install` en la raíz del repo.
- **Error de Stripe en checkout**
  - Revisar `STRIPE_SECRET_KEY`, `SITE_URL` y conectividad de red.
- **No responde `POST /api/redeem_grant`**
  - Confirmar que `ramia_core_plus.py` esté corriendo con `--web` y puerto correcto.

---

## 10) Comandos de verificación mínima (copy/paste)

```bash
python3 tokenomics_v1.py --self-test
python3 ramia_core_v1.py --datadir ./aichain_data_v1 mine miner_demo
python3 ramia_core_v1.py --datadir ./aichain_data_v1 status
python3 ramia_core_plus.py --guardian-model ./guardian_model.json --web --web-port 8787
```

Si necesitas un README adicional orientado a contribución (estilo `CONTRIBUTING.md`) con estándares de commits, release y CI, créalo separado de este README técnico.
