# INSTALL — RamIA Production v1

## 1) Requirements

- Python 3.10+
- Node.js 18+ (for Netlify functions local testing)
- pip + npm

## 2) Clone and install

```bash
git clone <your-repo-url>
cd RamIA
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -U pip cryptography
npm install
```

## 3) Prepare Guardian model

```bash
python3 aiguardian.py train --csv dataset.csv --out guardian_model.json
```

## 4) Run local node (Linux/macOS/Termux)

```bash
python3 ramia_core.py --guardian-model ./guardian_model.json --web --web-host 127.0.0.1 --web-port 8787
```

## 5) Run local node (Windows PowerShell)

```powershell
python ramia_core.py --guardian-model .\guardian_model.json --web --web-host 127.0.0.1 --web-port 8787
```

## 6) Run static site + Stripe functions locally

```bash
export SITE_URL=http://localhost:8888
export STRIPE_SECRET_KEY=sk_test_...
export STRIPE_WEBHOOK_SECRET=whsec_...
export STRIPE_GRANT_SECRET=change_me
export GRANT_FETCH_TTL_SECONDS=600
npx netlify dev
```

## 7) Retrieve + redeem grant token in local node

1. Complete checkout and keep the full success URL (it now includes `session_id` + `grant_key`).
2. Use the success page button (or call `/.netlify/functions/get_grant_token?session_id=...&grant_key=...`).
3. Redeem the returned token locally:

```bash
curl -s -X POST http://127.0.0.1:8787/api/redeem_grant \
  -H 'Content-Type: application/json' \
  -d '{"renter":"demo","token":"<paste_token_here>"}'
```

## API contract

- Endpoint: `POST /api/redeem_grant`
- Request body: `{"renter":"<id>","token":"<grant_token>"}`
- Success response: `{"ok":true,"renter":"<id>","credited":<int>,"credits_total":<int>}`
- Error response: `{"ok":false,"error":"<code>"}`
