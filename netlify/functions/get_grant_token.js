const crypto = require("crypto");
const { getGrant, deleteGrant } = require("./_grant_store");

function sha256Hex(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function safeEqualHex(a, b) {
  const left = Buffer.from(String(a || ""), "utf8");
  const right = Buffer.from(String(b || ""), "utf8");
  if (left.length !== right.length) return false;
  return crypto.timingSafeEqual(left, right);
}

exports.handler = async (event) => {
  const q = event.queryStringParameters || {};
  const sessionId = String(q.session_id || "").trim();
  const grantKey = String(q.grant_key || "").trim();
  const invalidateOnRead = String(q.invalidate_on_read || "1") !== "0";

  if (!sessionId) return { statusCode: 400, body: JSON.stringify({ error: "missing_session_id" }) };
  if (!grantKey) return { statusCode: 400, body: JSON.stringify({ error: "missing_grant_key" }) };

  const rec = await getGrant(sessionId);
  if (!rec) return { statusCode: 404, body: JSON.stringify({ error: "grant_not_found" }) };

  const expectedHash = String(rec.grant_key_hash || "");
  if (!expectedHash || !safeEqualHex(expectedHash, sha256Hex(grantKey))) {
    return { statusCode: 403, body: JSON.stringify({ error: "invalid_grant_key" }) };
  }

  const now = Math.floor(Date.now() / 1000);
  if (Number.isFinite(rec.fetch_expires_ts) && now > rec.fetch_expires_ts) {
    await deleteGrant(sessionId);
    return { statusCode: 410, body: JSON.stringify({ error: "grant_fetch_expired" }) };
  }

  const responseBody = JSON.stringify({ grant_token: rec.grant_token });
  if (invalidateOnRead) {
    await deleteGrant(sessionId);
  }

  return { statusCode: 200, body: responseBody };
};
