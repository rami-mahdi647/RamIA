# SECURITY — RamIA Production v1

## Secrets policy

- Never commit secrets, wallet keys, or `.env` files.
- Use environment variables for Stripe keys and webhook/grant secrets.
- Rotate `STRIPE_GRANT_SECRET` and `STRIPE_WEBHOOK_SECRET` if exposure is suspected.

## Wallet and local state

- Treat `wallet.json`, `market_secret.key`, and chain state files as sensitive.
- Store local runtime data on trusted devices only.
- Prefer full-disk encryption on production systems.

## Payments

- RamIA does not handle raw card data.
- All card input occurs on Stripe-hosted Checkout pages.
- Webhook signatures are verified before grant-token issuance.

## Token redemption

- Grant tokens are signed (HMAC-SHA256) and include expiry.
- Expired or tampered tokens are rejected by `stripe_bridge.py`.
- Redeem endpoint is local-node only by default (`127.0.0.1`).
