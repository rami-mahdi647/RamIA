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

function readFallbackFile() {
  if (!fs.existsSync(FALLBACK_FILE)) return {};
  return JSON.parse(fs.readFileSync(FALLBACK_FILE, "utf8"));
}

function writeFallbackFile(data) {
  fs.writeFileSync(FALLBACK_FILE, JSON.stringify(data, null, 2));
}

async function saveGrant(sessionId, grantRecord) {
  const store = await getBlobStore();
  if (store) {
    await store.setJSON(sessionId, grantRecord);
    return;
  }
  const existing = readFallbackFile();
  existing[sessionId] = grantRecord;
  writeFallbackFile(existing);
}

async function getGrant(sessionId) {
  const store = await getBlobStore();
  if (store) return await store.get(sessionId, { type: "json" });
  const existing = readFallbackFile();
  return existing[sessionId] || null;
}

async function deleteGrant(sessionId) {
  const store = await getBlobStore();
  if (store && typeof store.delete === "function") {
    await store.delete(sessionId);
    return;
  }
  const existing = readFallbackFile();
  if (!(sessionId in existing)) return;
  delete existing[sessionId];
  writeFallbackFile(existing);
}

module.exports = { saveGrant, getGrant, deleteGrant };
