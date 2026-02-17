import React, { useMemo, useState } from 'react'
import { ENV } from '../lib/env'
import { evmGetBalance, evmSendTx } from '../lib/evm'
import { useStore } from '../lib/store'
import axios from 'axios'

type Chain = 'eth'|'polygon'|'bnb'|'btc'|'cosmos'|'dag'

export default function Wallet(){
  const { btcAddr, setBtcAddr } = useStore()
  const [addr,setAddr] = useState(btcAddr)
  const [res,setRes] = useState<any>(null)

  const [evm, setEvm] = useState({ chain:'eth' as Chain, address:'', pk:'', amount:'' })
  const [cosmos, setCosmos] = useState({ address:'', mnemonic:'', to:'', amount:'' })
  const [btc, setBtc] = useState({ address:btcAddr, to:'', sats:'' })

  const onSaveBtc = ()=>{ setBtcAddr(addr); setRes({ok:true, msg:'BTC address guardada'}) }

  const evmBalance = async()=>{
    if (!evm.address) return;
    const b = await evmGetBalance(evm.address, evm.chain as any)
    setRes({ok:true, msg:`${b} ETH/MATIC/BNB (según red)`})
  }

  const evmSend = async()=>{
    try{
      const r = await evmSendTx(evm.pk, evm.to, evm.amount, evm.chain as any)
      setRes({ok:true, msg:`tx: ${r?.transactionHash||r?.hash}`})
    }catch(e:any){
      setRes({ok:false, msg:e.message})
    }
  }

  const btcBalance = async()=>{
    if (!btc.address) return;
    const { data } = await axios.get(`${ENV.BTC_API}/address/${btc.address}`)
    const chain = data.chain_stats||{}, memp = data.mempool_stats||{}
    const confirmed = (chain.funded_txo_sum||0)-(chain.spent_txo_sum||0)
    const unconf = (memp.funded_txo_sum||0)-(memp.spent_txo_sum||0)
    setRes({ok:true, msg:`${(confirmed/1e8).toFixed(8)} BTC (pendiente ${unconf} sats)`})
  }

  return (
    <div className="space-y-8">
      <div className="card">
        <div className="text-[#a9b9ff] mb-2">BTC</div>
        <div className="flex gap-2">
          <input className="input w-full" placeholder="bc1..." value={addr} onChange={e=>setAddr(e.target.value)}/>
          <button className="btn" onClick={onSaveBtc}>Guardar</button>
          <button className="btn" onClick={btcBalance}>Balance</button>
        </div>
      </div>

      <div className="card">
        <div className="text-[#a9b9ff] mb-2">EVM (Ethereum / Polygon / BNB)</div>
        <div className="grid md:grid-cols-5 gap-2">
          <select className="input" value={evm.chain} onChange={e=>setEvm({...evm, chain:e.target.value as any})}>
            <option value="eth">Ethereum</option>
            <option value="polygon">Polygon</option>
            <option value="bnb">BNB Chain</option>
          </select>
          <input className="input" placeholder="from address" value={evm.address} onChange={e=>setEvm({...evm,address:e.target.value})}/>
          <input className="input" type="password" placeholder="private key (no se guarda)" value={evm.pk} onChange={e=>setEvm({...evm,pk:e.target.value})}/>
          <input className="input" placeholder="to" value={evm.to} onChange={e=>setEvm({...evm,to:e.target.value})}/>
          <input className="input" placeholder="amount (ETH/MATIC/BNB)" value={evm.amount} onChange={e=>setEvm({...evm,amount:e.target.value})}/>
        </div>
        <div className="mt-2 flex gap-2">
          <button className="btn" onClick={evmBalance}>Balance</button>
          <button className="btn" onClick={evmSend}>Enviar</button>
        </div>
      </div>

      <div className="card">
        <div className="text-[#a9b9ff] mb-2">Cosmos (placeholder en navegador)</div>
        <div className="grid md:grid-cols-4 gap-2">
          <input className="input" placeholder="mnemonic (no se guarda)"/>
          <input className="input" placeholder="to"/>
          <input className="input" placeholder="amount (uatom)"/>
          <button className="btn">Enviar</button>
        </div>
        <div className="text-xs mt-2 opacity-75">* En escritorio, las operaciones Cosmos se ejecutan vía IPC para mayor seguridad.</div>
      </div>

      {res && <div className={"p-3 rounded-lg "+(res.ok? 'bg-green-950 border border-green-600':'bg-red-950 border border-red-600')}>{res.msg}</div>}
    </div>
  )
}
