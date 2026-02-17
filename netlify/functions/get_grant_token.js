const { getGrant } = require("./_grant_store");

exports.handler = async (event) => {
  const sessionId = String((event.queryStringParameters || {}).session_id || "").trim();
  if (!sessionId) return { statusCode: 400, body: JSON.stringify({ error: "missing_session_id" }) };
  const rec = await getGrant(sessionId);
  if (!rec) return { statusCode: 404, body: JSON.stringify({ error: "grant_not_found" }) };
  return { statusCode: 200, body: JSON.stringify(rec) };
};
