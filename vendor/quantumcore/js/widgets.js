const API = {
  base: 'https://mempool.space/api',
  address: (addr) => `${API.base}/address/${addr}`,
  blocks: () => `${API.base}/blocks`,
  mempool: () => `${API.base}/mempool`,
  fees: () => `${API.base}/v1/fees/recommended`,
  difficulty: () => `${API.base}/v1/difficulty-adjustment`
};

async function safeFetchJSON(url) {
  if (window.api && typeof window.api.fetchJSON === 'function') {
    try { return await window.api.fetchJSON(url); } catch (e) {}
  }
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return await r.json();
}

function satsToBTC(sats){ return (sats/1e8).toFixed(8); }
function fmt(n){ return new Intl.NumberFormat('es-ES').format(n); }

async function getAddressSummary(addr){
  const d = await safeFetchJSON(API.address(addr));
  const chain = d.chain_stats||{}, memp = d.mempool_stats||{};
  const confirmed = (chain.funded_txo_sum||0)-(chain.spent_txo_sum||0);
  const unconf = (memp.funded_txo_sum||0)-(memp.spent_txo_sum||0);
  return { confirmed, unconf, tx_count: (chain.tx_count||0)+(memp.tx_count||0) };
}
