import { create } from 'zustand'
export const useStore = create<{btcAddr:string,setBtcAddr:(v:string)=>void}>(set=>({
  btcAddr: localStorage.getItem('qc_btc_addr')||'',
  setBtcAddr:(v)=>{ localStorage.setItem('qc_btc_addr', v); set({ btcAddr: v }) }
}))
