# RamIA — Tokenomics v1 + Stripe Bot Renting

RamIA runs locally (Termux/PC/Mac/Windows) while Netlify serves only static PWA assets + serverless Stripe endpoints.

## What is included

- `docs/TOKENOMICS_V1.md`: canonical tokenomics spec for fixed supply `100,000,000 RAMIA`.
- `tokenomics_v1.py`: deterministic tokenomics math module + `--self-test`.
- `ramia_core_v1.py`: chain entrypoint that wraps `aichain` and applies emission adapter with `token_state.json`.
- `netlify/functions/create_checkout_session.js`: Stripe hosted Checkout session creation (`$1,000` fixed per bot).
- `netlify/functions/stripe_webhook.js`: webhook verification + signed grant token creation.
- `stripe_bridge.py`: local grant token verification and market credit apply helpers.
- `ramia_core_plus.py`: local node entrypoint exposing `POST /api/redeem_grant`.
- `site/`: static PWA with a dedicated `Rent Bots` page.
- `.github/workflows/release.yml`: tagged release builds via PyInstaller (Linux/Windows/macOS).
- `.github/workflows/check-site.yml`: CI check that fails if `site/index.html` is missing.

## Operational boundaries (quick guide)

- **Static frontend PWA (`site/`)**: installable app shell, offline cache (`sw.js`), manifest metadata, and browser UI (`index.html`, `rent-bots.html`, `success.html`).
- **Paid backend functions (`netlify/functions/`)**: Stripe Checkout creation, webhook validation, and secure token/grant delivery from Netlify serverless endpoints.
- **Local blockchain core (`aichain*`, `ramia_core*`, `aicore*`)**: local Python node execution, mining/state updates, and chain datadir persistence.

### Common symptom triage

| Symptom | First checks |
| --- | --- |
| `PWA does not install` | Inspect `site/sw.js` registration/caching behavior and verify manifest fields/icons in `site/manifest.webmanifest` (or the active manifest referenced by `site/index.html`). |
| `Checkout fails` | Validate Netlify function logs and environment variables (`STRIPE_SECRET_KEY`, `SITE_URL`, etc.) plus Stripe account/webhook setup. |
| `Chain/node failure` | Review local Python scripts (`ramia_core*`, `aichain*`, `aicore*`) and confirm `--datadir` path, permissions, and current chain state files. |

## Local test commands

### 1) Node run

```bash
python3 ramia_core_plus.py --guardian-model ./guardian_model.json --web
```

### 2) Tokenomics self-test

```bash
python3 tokenomics_v1.py --self-test
```

### 3) Tokenomics mining adapter sanity

```bash
python3 ramia_core_v1.py --datadir ./aichain_data_v1 mine miner_demo
python3 ramia_core_v1.py --datadir ./aichain_data_v1 status
```

### 4) Netlify functions local test (mocked request)

```bash
node -e "const fn=require('./netlify/functions/create_checkout_session'); fn.handler({httpMethod:'POST',body:JSON.stringify({renter:'demo',bots_count:2})}).then(x=>console.log(x.statusCode));"
```

> The command above is deterministic for input validation. A live Stripe session requires valid env vars and network.

---

## Final Checklist

### Netlify environment variables

Set in Netlify UI (Site settings → Environment variables):

- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `SITE_URL`
- Optional: `STRIPE_GRANT_SECRET` (recommended; if omitted webhook secret is reused)
- Optional: `BOT_RENT_PRICE_USD` (defaults to `1000`)

### Stripe webhook endpoint

Configure in Stripe Dashboard:

- Endpoint URL: `https://<your-site>.netlify.app/.netlify/functions/stripe_webhook`
- Event: `checkout.session.completed`
- Copy signing secret into `STRIPE_WEBHOOK_SECRET`

### Local node redeem flow

1. Complete checkout on hosted Stripe page.
2. Open `success.html?session_id=...`.
3. Fetch grant token from `/.netlify/functions/get_grant_token`.
4. Redeem on the local node using the official contract:

```bash
curl -X POST http://127.0.0.1:8787/api/redeem_grant \
  -H 'Content-Type: application/json' \
  -d '{"renter":"demo","token":"<grant_token_here>"}'
```

### API contract

**Endpoint**: `POST /api/redeem_grant`

**Request JSON**

```json
{
  "renter": "string (required)",
  "token": "string (required, signed grant token)"
}
```

**Response JSON**

```json
{
  "ok": true,
  "renter": "demo",
  "credited": 2000,
  "credits_total": 5000
}
```

Error responses follow the shape `{"ok": false, "error": "<code>"}` (for example: `missing_renter_or_token`, `renter_mismatch`, `expired_token`).

### Security notes

- Raw card data is never handled by RamIA; checkout is Stripe-hosted only.
- All secrets come from environment variables; do not hardcode keys.
- Webhook signatures are verified before grant issuance.
- Grant tokens are HMAC-signed and expire (`expires_ts`).
- Local redemption validates token integrity and renter match before crediting.
