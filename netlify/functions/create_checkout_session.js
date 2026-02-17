const Stripe = require("stripe");
const crypto = require("crypto");

function parseBody(event) {
  if (!event.body) return {};
  try {
    return JSON.parse(event.isBase64Encoded ? Buffer.from(event.body, "base64").toString("utf8") : event.body);
  } catch (_) {
    return {};
  }
}

function toPositiveInt(value, fallback) {
  const n = Number.parseInt(String(value), 10);
  if (!Number.isFinite(n) || n <= 0) return fallback;
  return n;
}

function sha256Hex(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

exports.handler = async (event) => {
  try {
    if (event.httpMethod && event.httpMethod !== "POST") {
      return { statusCode: 405, body: JSON.stringify({ error: "method_not_allowed" }) };
    }

    const stripeKey = process.env.STRIPE_SECRET_KEY;
    const siteUrl = process.env.SITE_URL;
    if (!stripeKey || !siteUrl) {
      return { statusCode: 500, body: JSON.stringify({ error: "server_not_configured" }) };
    }

    const input = parseBody(event);
    const renter = String(input.renter || "").replace(/[^a-zA-Z0-9_\-.]/g, "").slice(0, 80);
    const botsCount = toPositiveInt(input.bots_count, 1);
    if (!renter) return { statusCode: 400, body: JSON.stringify({ error: "invalid_renter" }) };

    const pricePerBotUsd = toPositiveInt(process.env.BOT_RENT_PRICE_USD || "1000", 1000);
    const unitAmount = pricePerBotUsd * 100 * botsCount;
    const grantLookupKey = crypto.randomBytes(18).toString("base64url");
    const grantLookupHash = sha256Hex(grantLookupKey);

    const stripe = new Stripe(stripeKey, { apiVersion: "2024-06-20" });
    const session = await stripe.checkout.sessions.create({
      mode: "payment",
      line_items: [
        {
          quantity: 1,
          price_data: {
            currency: "usd",
            unit_amount: unitAmount,
            product_data: {
              name: "RamIA Bot Renting",
              description: `${botsCount} bot(s) rental at $${pricePerBotUsd}/bot`,
            },
          },
        },
      ],
      metadata: {
        renter,
        bots_count: String(botsCount),
        purpose: "bot_rent_v1",
        grant_key_hash: grantLookupHash,
      },
      success_url: `${siteUrl}/success.html?session_id={CHECKOUT_SESSION_ID}&grant_key=${encodeURIComponent(grantLookupKey)}`,
      cancel_url: `${siteUrl}/cancel.html`,
    });

    return {
      statusCode: 200,
      body: JSON.stringify({ checkout_url: session.url, session_id: session.id }),
    };
  } catch (err) {
    return { statusCode: 500, body: JSON.stringify({ error: "stripe_checkout_failed", details: err.message }) };
  }
};
