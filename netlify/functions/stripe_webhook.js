const Stripe = require("stripe");
const crypto = require("crypto");
const { saveGrant } = require("./_grant_store");

function b64url(input) {
  return Buffer.from(input).toString("base64url");
}

function signGrant(payload, secret) {
  const header = { alg: "HS256", typ: "RGT" };
  const encHeader = b64url(JSON.stringify(header));
  const encPayload = b64url(JSON.stringify(payload));
  const data = `${encHeader}.${encPayload}`;
  const sig = crypto.createHmac("sha256", secret).update(data).digest("base64url");
  return `${data}.${sig}`;
}

exports.handler = async (event) => {
  try {
    const stripeKey = process.env.STRIPE_SECRET_KEY;
    const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;
    const grantSecret = process.env.STRIPE_GRANT_SECRET || webhookSecret;
    if (!stripeKey || !webhookSecret || !grantSecret) {
      return { statusCode: 500, body: "missing_stripe_env" };
    }

    const stripe = new Stripe(stripeKey, { apiVersion: "2024-06-20" });
    const sig = event.headers["stripe-signature"] || event.headers["Stripe-Signature"];
    const body = event.isBase64Encoded ? Buffer.from(event.body || "", "base64").toString("utf8") : (event.body || "");
    const stripeEvent = stripe.webhooks.constructEvent(body, sig, webhookSecret);

    if (stripeEvent.type === "checkout.session.completed") {
      const session = stripeEvent.data.object;
      const md = session.metadata || {};
      if (String(md.purpose || "") !== "bot_rent_v1") {
        return { statusCode: 200, body: JSON.stringify({ received: true, ignored: "purpose_mismatch" }) };
      }

      const renter = String(md.renter || "").trim();
      const botsCount = Math.max(1, Number.parseInt(md.bots_count || "1", 10));
      const now = Math.floor(Date.now() / 1000);
      const creditsToAdd = botsCount;
      const expiresTs = now + (30 * 24 * 3600);
      const grantFetchTtlSeconds = Math.max(60, Number.parseInt(process.env.GRANT_FETCH_TTL_SECONDS || "600", 10));
      const fetchExpiresTs = now + grantFetchTtlSeconds;

      const payload = {
        jti: crypto.randomUUID(),
        session_id: session.id,
        renter,
        bots_count: botsCount,
        credits_to_add: creditsToAdd,
        purpose: "bot_rent_v1",
        iat: now,
        expires_ts: expiresTs,
      };
      const grantToken = signGrant(payload, grantSecret);

      await saveGrant(session.id, {
        grant_token: grantToken,
        grant_key_hash: String(md.grant_key_hash || ""),
        fetch_expires_ts: fetchExpiresTs,
      });
    }

    return { statusCode: 200, body: JSON.stringify({ received: true }) };
  } catch (err) {
    return { statusCode: 400, body: `Webhook error: ${err.message}` };
  }
};
