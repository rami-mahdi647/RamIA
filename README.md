# RamIA — Production v1

RamIA is a local-first AI node stack with a static Netlify website, PWA docs/download portal, and Stripe-hosted checkout flow for bot rental credits.

## Production v1 contents

- `/site`: production static website (Netlify-ready PWA).
- `/netlify/functions`: Stripe checkout + webhook + grant-token retrieval.
- `ramia_core.py`: new runtime entrypoint with `/api/redeem_grant_token` endpoint.
- `stripe_bridge.py`: verification bridge that validates grant tokens and credits renter accounts.
- `.github/workflows/release.yml`: builds **Software v1** binaries via PyInstaller on Linux/Windows/macOS for tags `v*.*.*`.

## Quick links

- Website entrypoint: `site/index.html`
- Stripe setup guide: `STRIPE_SETUP.md`
- Installation guide: `INSTALL.md`
- Security policy: `SECURITY.md`

## Local run (node)

```bash
python3 ramia_core.py --guardian-model ./guardian_model.json --web
```

Then open `http://127.0.0.1:8787`.

## Local run (site + functions)

```bash
npm install
npx netlify dev
```

This serves static files from `/site` and functions from `/netlify/functions`.

## Payment and redemption flow

1. Frontend calls `/.netlify/functions/create_checkout_session`.
2. User pays on Stripe-hosted Checkout.
3. Stripe sends `checkout.session.completed` to `/.netlify/functions/stripe_webhook`.
4. Webhook creates signed grant token and stores by session ID.
5. `success.html` fetches token from `/.netlify/functions/get_grant_token`.
6. User redeems token on local node via `/api/redeem_grant_token`.

## Release automation

Push a semver tag:

```bash
git tag v1.0.0
git push origin v1.0.0
```

GitHub Actions builds and uploads release assets named `Software-v1-<os>`.
