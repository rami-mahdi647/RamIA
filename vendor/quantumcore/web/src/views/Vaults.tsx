import React, { useEffect, useMemo, useState } from 'react'
import axios from 'axios'
import { ENV } from '../lib/env'

type Block = {
  id: string
  height: number
  timestamp: number
  tx_count?: number
  size?: number
  weight?: number
}

const AVG_BLOCK_TIME_SECONDS = 10 * 60

function formatCountdown(totalSeconds: number){
  const safe = Math.max(0, totalSeconds)
  const mm = Math.floor(safe / 60)
  const ss = safe % 60
  return `${mm}m ${String(ss).padStart(2, '0')}s`
}

function shortHash(hash?: string){
  if (!hash) return '—'
  if (hash.length <= 16) return hash
  return `${hash.slice(0, 12)}…${hash.slice(-12)}`
}

export default function Vaults(){
  const [blocks, setBlocks] = useState<Block[]>([])
  const [mempool, setMempool] = useState<any>(null)
  const [now, setNow] = useState(Date.now())

  useEffect(()=>{
    const tick = async()=>{
      try{
        const [b,m] = await Promise.all([
          axios.get(`${ENV.BTC_API}/blocks`),
          axios.get(`${ENV.BTC_API}/mempool`)
        ])
        setBlocks((b.data || []) as Block[])
        setMempool(m.data)
      }catch{}
    }

    tick()
    const fetchId = setInterval(tick, 30000)
    const clockId = setInterval(()=>setNow(Date.now()), 1000)
    return ()=>{
      clearInterval(fetchId)
      clearInterval(clockId)
    }
  },[])

  const latest = blocks[0]
  const lastBlockMs = latest ? latest.timestamp * 1000 : 0
  const elapsedSeconds = lastBlockMs ? Math.floor((now - lastBlockMs) / 1000) : 0
  const remainingSeconds = Math.max(0, AVG_BLOCK_TIME_SECONDS - elapsedSeconds)

  const estimatedNextBlockDate = useMemo(()=>{
    if (!lastBlockMs) return null
    return new Date(lastBlockMs + AVG_BLOCK_TIME_SECONDS * 1000)
  }, [lastBlockMs])

  const minedPct = Math.min(100, Math.round((elapsedSeconds / AVG_BLOCK_TIME_SECONDS) * 100))

  return (
    <div className="space-y-6">
      <div className='badge'>Vaults & Minería</div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="panel p-4 space-y-3">
          <div className="text-[#a9b9ff] border-b border-[#1b2340] pb-2">Estado de minado (tiempo real)</div>
          <div>
            <div className="text-sm text-[#93a3d6]">Altura actual</div>
            <div className="text-3xl font-bold">{latest ? `#${latest.height}` : '—'}</div>
          </div>
          <div>
            <div className="text-sm text-[#93a3d6]">Hash del último bloque</div>
            <div className="font-mono text-sm break-all">{shortHash(latest?.id)}</div>
          </div>
          <div>
            <div className="text-sm text-[#93a3d6]">Último bloque minado</div>
            <div>{latest ? new Date(latest.timestamp * 1000).toLocaleString() : '—'}</div>
          </div>
          <div>
            <div className="text-sm text-[#93a3d6]">Estimación próximo bloque</div>
            <div className="font-semibold">{estimatedNextBlockDate ? estimatedNextBlockDate.toLocaleString() : '—'}</div>
            <div className="text-[#93a3d6] text-sm">Cuenta regresiva: {latest ? formatCountdown(remainingSeconds) : '—'}</div>
          </div>
          <div>
            <div className="h-2 rounded-full bg-[#1b2340] overflow-hidden">
              <div className="h-full bg-gradient-to-r from-blue-600 to-cyan-400" style={{ width: `${latest ? minedPct : 0}%` }} />
            </div>
            <div className="text-xs text-[#93a3d6] mt-1">Progreso estimado del ciclo de 10 min: {latest ? `${minedPct}%` : '—'}</div>
          </div>
        </div>

        <div className="panel p-4 space-y-3">
          <div className="text-[#a9b9ff] border-b border-[#1b2340] pb-2">Red Bitcoin</div>
          <div className="flex justify-between"><span className="text-[#93a3d6]">Transacciones en mempool</span><b>{mempool ? mempool.count.toLocaleString() : '—'}</b></div>
          <div className="flex justify-between"><span className="text-[#93a3d6]">Tamaño mempool</span><b>{mempool ? (mempool.vsize/1e6).toFixed(2) : '—'} vMB</b></div>
          <div className="flex justify-between"><span className="text-[#93a3d6]">TX último bloque</span><b>{latest?.tx_count?.toLocaleString?.() ?? '—'}</b></div>
          <div className="flex justify-between"><span className="text-[#93a3d6]">Peso último bloque</span><b>{latest?.weight?.toLocaleString?.() ?? '—'}</b></div>
          <div className="text-xs text-[#93a3d6]">Datos en vivo desde mempool.space API.</div>
        </div>
      </div>
    </div>
  )
}
