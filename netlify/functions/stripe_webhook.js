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
      return { statusCode: 500, body: "Missing Stripe configuration" };
    }

    const stripe = new Stripe(stripeKey, { apiVersion: "2024-06-20" });
    const signature = event.headers["stripe-signature"] || event.headers["Stripe-Signature"];
    const body = event.isBase64Encoded ? Buffer.from(event.body || "", "base64").toString("utf8") : (event.body || "");
    const stripeEvent = stripe.webhooks.constructEvent(body, signature, webhookSecret);

    if (stripeEvent.type === "checkout.session.completed") {
      const session = stripeEvent.data.object;
      const md = session.metadata || {};
      const renter = String(md.renter || "");
      const credits = Math.max(1, Number.parseInt(md.credits || "0", 10));
      const durationSec = Math.max(60, Number.parseInt(md.duration || "3600", 10));
      const now = Math.floor(Date.now() / 1000);
      const payload = {
        jti: crypto.randomUUID(),
        session_id: session.id,
        renter,
        tier: String(md.tier || "Silver"),
        credits,
        iat: now,
        expires_at: now + durationSec,
      };
      const grantToken = signGrant(payload, grantSecret);
      await saveGrant(session.id, {
        grant_token: grantToken,
        renter,
        credits,
        expires_at: payload.expires_at,
        paid_at: now,
      });
    }

    return { statusCode: 200, body: JSON.stringify({ received: true }) };
  } catch (err) {
    return { statusCode: 400, body: `Webhook error: ${err.message}` };
  }
};
