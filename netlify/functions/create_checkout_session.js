const Stripe = require("stripe");

const ALLOWED_TIERS = new Set(["Bronze", "Silver", "Gold", "Platinum"]);

function asInt(input, fallback) {
  const n = Number.parseInt(String(input), 10);
  return Number.isFinite(n) ? n : fallback;
}

exports.handler = async (event) => {
  try {
    const key = process.env.STRIPE_SECRET_KEY;
    const siteUrl = process.env.SITE_URL;
    if (!key || !siteUrl) return { statusCode: 500, body: JSON.stringify({ error: "server_not_configured" }) };

    const stripe = new Stripe(key, { apiVersion: "2024-06-20" });
    const qs = event.queryStringParameters || {};
    const renter = String(qs.renter || "").replace(/[^a-zA-Z0-9_\-.]/g, "").slice(0, 80);
    const tier = String(qs.tier || "Silver");
    const credits = Math.max(1, Math.min(1000000, asInt(qs.credits, 1000)));
    const duration = Math.max(60, Math.min(31536000, asInt(qs.duration, 3600)));

    if (!renter) return { statusCode: 400, body: JSON.stringify({ error: "invalid_renter" }) };
    if (!ALLOWED_TIERS.has(tier)) return { statusCode: 400, body: JSON.stringify({ error: "invalid_tier" }) };

    const unitAmount = Math.max(50, credits * 5); // 0.05 USD per credit minimum order 0.50

    const session = await stripe.checkout.sessions.create({
      mode: "payment",
      line_items: [{
        quantity: 1,
        price_data: {
          currency: "usd",
          unit_amount: unitAmount,
          product_data: { name: "Bot rental credits", description: `${tier} tier credits for renter ${renter}` }
        }
      }],
      metadata: { renter, tier, credits: String(credits), duration: String(duration) },
      success_url: `${siteUrl}/success.html?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${siteUrl}/cancel.html`
    });

    return { statusCode: 200, body: JSON.stringify({ checkout_url: session.url, session_id: session.id }) };
  } catch (err) {
    return { statusCode: 500, body: JSON.stringify({ error: "stripe_checkout_failed", details: err.message }) };
  }
};
