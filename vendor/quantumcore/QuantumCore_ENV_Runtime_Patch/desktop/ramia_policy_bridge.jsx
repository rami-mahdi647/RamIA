// ramia_policy_bridge.js
// Bridge to RamIA Policy Sidecar (http://127.0.0.1:8787)
//
// Requires: node >= 18 (fetch available). If not, fallback to axios.

const POLICY_URL = process.env.RAMIA_POLICY_URL || "http://127.0.0.1:8787";

async function postJSON(path, body) {
  const url = `${POLICY_URL}${path}`;
  // Prefer fetch (Node 18+)
  if (typeof fetch === "function") {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(`Policy HTTP ${r.status}: ${JSON.stringify(j)}`);
    return j;
  }
  // Fallback: axios if present
  const axios = require("axios");
  const r = await axios.post(url, body, { timeout: 8000 });
  return r.data;
}

async function txPolicy({ amount, fee, outputs, memo, to_addr }) {
  return await postJSON("/tx_policy", {
    amount: amount ?? 0,
    fee: fee ?? 0,
    outputs: outputs ?? 1,
    memo: memo ?? "",
    to_addr: to_addr ?? "",
    timestamp: Math.floor(Date.now() / 1000),
  });
}

async function blockReward(metrics) {
  return await postJSON("/block_reward", metrics);
}

module.exports = { txPolicy, blockReward, POLICY_URL };
