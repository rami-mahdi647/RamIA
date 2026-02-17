import React, { useEffect, useState } from 'react'
import axios from 'axios'
import { ENV } from '../lib/env'
import { useStore } from '../lib/store'

export default function Dashboard(){
  const { btcAddr } = useStore()
  const [mempool, setMempool] = useState<any>(null)
  const [fees, setFees] = useState<any>(null)
  const [blocks, setBlocks] = useState<any[]>([])
  const [bal, setBal] = useState<string>('—')
  const [pend, setPend] = useState<string>('—')

  useEffect(()=>{
    const tick = async()=>{
      try{
        const [m,f,b] = await Promise.all([
          axios.get(`${ENV.BTC_API}/mempool`),
          axios.get(`${ENV.BTC_API}/v1/fees/recommended`),
          axios.get(`${ENV.BTC_API}/blocks`)
        ])
        setMempool(m.data); setFees(f.data); setBlocks(b.data||[])
        if (btcAddr){
          const r = await axios.get(`${ENV.BTC_API}/address/${btcAddr}`)
          const chain = r.data.chain_stats||{}, memp = r.data.mempool_stats||{}
          const confirmed = (chain.funded_txo_sum||0)-(chain.spent_txo_sum||0)
          const unconf = (memp.funded_txo_sum||0)-(memp.spent_txo_sum||0)
          setBal((confirmed/1e8).toFixed(8)); setPend(`${unconf} sats`)
        }
      }catch{}
    }
    tick(); const id=setInterval(tick, 30000); return ()=>clearInterval(id)
  },[btcAddr])

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="card">
          <div className="text-[#a9b9ff] mb-2">Saldo BTC</div>
          <div className="text-3xl font-bold">{bal} <small>BTC</small></div>
          <div className="text-[#93a3d6]">Pendiente: {pend}</div>
        </div>
        <div className="card">
          <div className="text-[#a9b9ff] mb-2">Mempool</div>
          <div className="text-3xl font-bold">{mempool? mempool.count.toLocaleString() : '—'} <small>tx</small></div>
          <div className="text-[#93a3d6]">Tamaño: {mempool? (mempool.vsize/1e6).toFixed(2):'—'} vMB</div>
        </div>
        <div className="card">
          <div className="text-[#a9b9ff] mb-2">Tarifas</div>
          <div className="flex gap-6">
            <div><b>Lento</b><div>{fees? fees.hourFee:'—'} sat/vB</div></div>
            <div><b>Medio</b><div>{fees? fees.halfHourFee:'—'} sat/vB</div></div>
            <div><b>Rápido</b><div>{fees? fees.fastestFee:'—'} sat/vB</div></div>
          </div>
          <div className="text-[#93a3d6]">Fuente: mempool.space</div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="panel p-4 md:col-span-2">
          <div className="border-b border-[#1b2340] pb-3 mb-3 text-[#a9b9ff]">Últimos bloques</div>
          <ul className="grid grid-cols-2 gap-3">
            {blocks.slice(0,8).map(b=>(
              <li key={b.id} className="bg-[#0f1426] border border-[#1b2340] rounded-xl p-3">
                <b>#{b.height}</b><br/>
                <small>{new Date(b.timestamp*1000).toLocaleString()}</small><br/>
                <small>TX: {b.tx_count?.toLocaleString()}</small>
              </li>
            ))}
          </ul>
        </div>
        <div className="panel p-4">
          <div className="border-b border-[#1b2340] pb-3 mb-3 text-[#a9b9ff]">Señales</div>
          <div className="space-y-3">
            <div className="badge">On‑chain OK</div>
            <div className="badge">Modelo: pending feed</div>
          </div>
        </div>
      </div>
    </div>
  )
}
