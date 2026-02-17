# Stripe Setup for RamIA Production v1

## Architecture

- Checkout is created in Netlify Function `create_checkout_session`.
- Stripe webhook is handled by `stripe_webhook`.
- Grant token is fetched by `get_grant_token` and redeemed locally in `ramia_core.py`.

## Environment variables

Set in Netlify site settings (Build & deploy → Environment):

- `SITE_URL` = your deployed site URL (example: `https://ramia.netlify.app`)
- `STRIPE_SECRET_KEY` = Stripe secret key (`sk_live_...` or `sk_test_...`)
- `STRIPE_WEBHOOK_SECRET` = webhook signing secret (`whsec_...`)
- `STRIPE_GRANT_SECRET` = dedicated HMAC key for grant tokens (recommended)

## Stripe Dashboard configuration

1. Create or use your Stripe account.
2. Use hosted Checkout (no direct card capture in RamIA).
3. Add webhook endpoint:
   - URL: `https://<your-site>.netlify.app/.netlify/functions/stripe_webhook`
   - Events: `checkout.session.completed`
4. Copy webhook signing secret into `STRIPE_WEBHOOK_SECRET`.

## Test mode flow

1. Set all env vars to test keys/secrets.
2. Trigger checkout via:
   `/.netlify/functions/create_checkout_session?renter=alice&tier=Gold&credits=1000&duration=3600`
3. Complete payment with Stripe test card.
4. Open `/success.html?session_id=<id>` and load the grant token.
5. Redeem token on local RamIA node endpoint `/api/redeem_grant_token`.
