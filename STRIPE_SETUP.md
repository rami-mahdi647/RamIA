# Stripe Setup for RamIA Production v1

## Architecture

- Checkout is created in Netlify Function `create_checkout_session`.
- Stripe webhook is handled by `stripe_webhook`.
- Grant token is fetched by `get_grant_token` and redeemed locally in `ramia_core.py`.
- Grant retrieval requires **two factors**: `session_id` + temporary `grant_key`.

## Environment variables

Set in Netlify site settings (Build & deploy → Environment):

- `SITE_URL` = your deployed site URL (example: `https://ramia.netlify.app`)
- `STRIPE_SECRET_KEY` = Stripe secret key (`sk_live_...` or `sk_test_...`)
- `STRIPE_WEBHOOK_SECRET` = webhook signing secret (`whsec_...`)
- `STRIPE_GRANT_SECRET` = dedicated HMAC key for grant tokens (recommended)
- `GRANT_FETCH_TTL_SECONDS` = short-lived retrieval TTL for `get_grant_token` (default `600`)

## Stripe Dashboard configuration

1. Create or use your Stripe account.
2. Use hosted Checkout (no direct card capture in RamIA).
3. Add webhook endpoint:
   - URL: `https://<your-site>.netlify.app/.netlify/functions/stripe_webhook`
   - Events: `checkout.session.completed`
4. Copy webhook signing secret into `STRIPE_WEBHOOK_SECRET`.

## Test mode flow

1. Set all env vars to test keys/secrets.
2. Trigger checkout via your app (or `/.netlify/functions/create_checkout_session` POST).
3. Complete payment with Stripe test card.
4. Open `/success.html?session_id=<id>` and load the grant token.
5. Redeem token on local RamIA node endpoint `POST /api/redeem_grant` using JSON body `{"renter":"alice","token":"<grant_token>"}`.

## API contract

Use a single redemption contract across docs/UI/backend:

- **HTTP**: `POST /api/redeem_grant`
- **Request JSON**: `renter` (string, required), `token` (string, required)
- **Success JSON**: `ok`, `renter`, `credited`, `credits_total`
- **Error JSON**: `ok=false` with `error` code

4. Open the full redirect URL: `/success.html?session_id=<id>&grant_key=<temp_key>`.
5. Call `/.netlify/functions/get_grant_token?session_id=<id>&grant_key=<temp_key>`.
6. Endpoint returns only `{ "grant_token": "..." }` and invalidates the grant after the first successful read by default.
7. Redeem token on local RamIA node endpoint `/api/redeem_grant_token`.
