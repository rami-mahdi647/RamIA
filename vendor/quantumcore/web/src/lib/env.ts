export const ENV = {
  ETH_RPC: import.meta.env.VITE_ETH_RPC || '',
  POLYGON_RPC: import.meta.env.VITE_POLYGON_RPC || '',
  BNB_RPC: import.meta.env.VITE_BNB_RPC || '',
  COSMOS_RPC: import.meta.env.VITE_COSMOS_RPC || '',
  COSMOS_CHAIN_ID: import.meta.env.VITE_COSMOS_CHAIN_ID || 'cosmoshub-4',
  COSMOS_DENOM: import.meta.env.VITE_COSMOS_DENOM || 'uatom',
  BTC_API: import.meta.env.VITE_BTC_API || 'https://mempool.space/api',
  DAG_NODE: import.meta.env.VITE_DAG_NODE || ''
}
