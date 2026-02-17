const fs = require("fs");
const path = require("path");

const FALLBACK_FILE = path.join(process.cwd(), ".netlify-grants.json");

async function getBlobStore() {
  try {
    const blobs = require("@netlify/blobs");
    if (typeof blobs.getStore === "function") return blobs.getStore("ramia-grants");
  } catch (_) {}
  return null;
}

async function saveGrant(sessionId, grantRecord) {
  const store = await getBlobStore();
  if (store) {
    await store.setJSON(sessionId, grantRecord);
    return;
  }
  const existing = fs.existsSync(FALLBACK_FILE)
    ? JSON.parse(fs.readFileSync(FALLBACK_FILE, "utf8"))
    : {};
  existing[sessionId] = grantRecord;
  fs.writeFileSync(FALLBACK_FILE, JSON.stringify(existing, null, 2));
}

async function getGrant(sessionId) {
  const store = await getBlobStore();
  if (store) return await store.get(sessionId, { type: "json" });
  if (!fs.existsSync(FALLBACK_FILE)) return null;
  const existing = JSON.parse(fs.readFileSync(FALLBACK_FILE, "utf8"));
  return existing[sessionId] || null;
}

module.exports = { saveGrant, getGrant };
