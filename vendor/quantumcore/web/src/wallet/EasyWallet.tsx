
import React, { useEffect, useState } from 'react'
import { newMnemonic, isMnemonicValid, seedFromMnemonic } from '../lib/hd'
import { vaultSave, vaultLoad, vaultDelete } from '../lib/secure'
import { ENV } from '../lib/env'

declare global {
  interface Window {
    bridge?: any
  }
}

function Section({title, children}:{title:string, children:React.ReactNode}){
  return (
    <div className="card space-y-3">
      <div className="text-[#a9b9ff]">{title}</div>
      <div>{children}</div>
    </div>
  )
}

type SendResult = { ok:boolean, msg:string }

export default function EasyWallet(){
  const [hasVault, setHasVault] = useState(false)
  const [mnemonic, setMnemonic] = useState('')
  const [confirm, setConfirm] = useState(false)
  const [pass, setPass] = useState('')
  const [index, setIndex] = useState(0)
  const [addrs, setAddrs] = useState<any[]>([])
  const [res, setRes] = useState<SendResult|null>(null)

  useEffect(()=>{ (async()=>{
    const s = await vaultLoad().catch(()=>null)
    if (s) { setHasVault(true); await refreshAddrs(0) }
  })() }, [])

  async function refreshAddrs(i:number){
    if (window.bridge?.wallet?.derive){
      const rows = await window.bridge.wallet.derive(i)
      setAddrs(rows||[])
    }
  }

  const onCreate = ()=>{
    const m = newMnemonic(12); setMnemonic(m); setConfirm(false)
  }
  const onSave = async()=>{
    if (!mnemonic || !isMnemonicValid(mnemonic)) { setRes({ok:false, msg:'Frase inválida'}) ; return }
    if (!pass || pass.length < 6) { setRes({ok:false, msg:'Contraseña local mínima 6 chars'}); return }
    const s = seedFromMnemonic(mnemonic)
    const ok = await vaultSave(s, pass).catch(()=>false)
    if (ok){ setHasVault(true); await refreshAddrs(0); setRes({ok:true, msg:'Monedero creado'}) }
    else setRes({ok:false, msg:'No se pudo guardar'})
  }
  const onLoad = async()=>{
    if (!pass){ setRes({ok:false, msg:'Introduce contraseña local'}) ; return }
    const s = await vaultLoad(pass).catch(()=>null)
    if (!s){ setRes({ok:false, msg:'No se pudo desbloquear'}); return }
    setHasVault(true); await refreshAddrs(0); setRes({ok:true, msg:'Desbloqueado'}) 
  }
  const onWipe = async()=>{ await vaultDelete(); setHasVault(false); setAddrs([]); setRes({ok:true, msg:'Eliminado del dispositivo'}) }
  const onNewAddr = async()=>{ const i = index+1; setIndex(i); await refreshAddrs(i) }

  // SEND forms
  const [evm, setEvm] = useState({ chain:'eth', to:'', amount:'' })
  const [btc, setBtc] = useState({ to:'', sats:'', feeRate:'15' })
  const [cosmos, setCosmos] = useState({ to:'', amount:'' })

  const sendEvm = async()=>{
    try{
      const payload = { chain: evm.chain, index, to: evm.to, amount: evm.amount }
      const out = await window.bridge.wallet.evmSend(payload, ENV)
      setRes({ok:true, msg:`EVM tx: ${out.hash}`})
    }catch(e:any){ setRes({ok:false, msg: e.message||String(e)}) }
  }
  const sendBtc = async()=>{
    try{
      const payload = { index, to: btc.to, amountSats: Number(btc.sats), feeRate: Number(btc.feeRate||15) }
      const out = await window.bridge.wallet.btcSend(payload, ENV)
      setRes({ok:true, msg:`BTC txid: ${out.txid}`})
    }catch(e:any){ setRes({ok:false, msg: e.message||String(e)}) }
  }
  const sendCosmos = async()=>{
    try{
      const payload = { index, to: cosmos.to, amountUatom: String(cosmos.amount) }
      const out = await window.bridge.wallet.cosmosSend(payload, ENV)
      setRes({ok:true, msg:`COSMOS: ${out.transactionHash || 'ok'}`})
    }catch(e:any){ setRes({ok:false, msg: e.message||String(e)}) }
  }

  return (
    <div className="space-y-6">
      {!hasVault && (
        <>
          <Section title="Crear monedero (1 clic)">
            <button className="btn" onClick={onCreate}>Generar frase (12 palabras)</button>
            {mnemonic && (
              <div className="mt-3">
                <div className="p-3 rounded-lg bg-[#0f1426] border border-[#1b2340]">{mnemonic}</div>
                <label className="flex gap-2 items-center mt-3">
                  <input type="checkbox" checked={confirm} onChange={e=>setConfirm(e.target.checked)}/>
                  <span>He guardado la frase en lugar seguro</span>
                </label>
                <div className="mt-3 flex gap-2">
                  <input className="input" type="password" placeholder="Contraseña local (cifrado)"
                    value={pass} onChange={e=>setPass(e.target.value)}/>
                  <button className="btn" disabled={!confirm} onClick={onSave}>Guardar</button>
                </div>
              </div>
            )}
          </Section>

          <Section title="Desbloquear / Restaurar">
            <textarea className="input w-full" rows={2} placeholder="Frase de 12 palabras (si vas a restaurar)"
              value={mnemonic} onChange={e=>setMnemonic(e.target.value)}/>
            <div className="flex gap-2">
              <input className="input" type="password" placeholder="Contraseña local"
                value={pass} onChange={e=>setPass(e.target.value)}/>
              <button className="btn" onClick={onLoad}>Desbloquear</button>
              <button className="btn" onClick={onSave}>Restaurar y guardar</button>
            </div>
          </Section>
        </>
      )}

      {hasVault && (
        <>
          <Section title="Direcciones derivadas (cuenta 0)">
            <div className="flex gap-2 items-center">
              <button className="btn" onClick={onNewAddr}>Nueva dirección (índice {index+1})</button>
              <button className="btn" onClick={onWipe}>Eliminar de este dispositivo</button>
            </div>
            <ul className="mt-3 space-y-2">
              {addrs.map((a:any,i:number)=>(
                <li key={i} className="p-3 rounded-lg bg-[#0f1426] border border-[#1b2340]">
                  <b className="mr-2">{a.chain.toUpperCase()}</b>
                  <code className="break-all">{a.address}</code>
                  <span className="ml-2 text-xs opacity-70">{a.path}</span>
                </li>
              ))}
            </ul>
          </Section>

          <Section title="Enviar (EVM: ETH/Polygon/BNB)">
            <div className="grid md:grid-cols-4 gap-2">
              <select className="input" value={evm.chain} onChange={e=>setEvm({...evm, chain:e.target.value})}>
                <option value="eth">Ethereum</option>
                <option value="polygon">Polygon</option>
                <option value="bnb">BNB</option>
              </select>
              <input className="input" placeholder="to 0x..." value={evm.to} onChange={e=>setEvm({...evm,to:e.target.value})}/>
              <input className="input" placeholder="amount (ETH/MATIC/BNB)" value={evm.amount} onChange={e=>setEvm({...evm,amount:e.target.value})}/>
              <button className="btn" onClick={sendEvm}>Enviar</button>
            </div>
          </Section>

          <Section title="Enviar (BTC P2WPKH)">
            <div className="grid md:grid-cols-4 gap-2">
              <input className="input" placeholder="to bc1..." value={btc.to} onChange={e=>setBtc({...btc,to:e.target.value})}/>
              <input className="input" placeholder="sats" value={btc.sats} onChange={e=>setBtc({...btc,sats:e.target.value})}/>
              <input className="input" placeholder="feeRate sat/vB (≈15)" value={btc.feeRate} onChange={e=>setBtc({...btc,feeRate:e.target.value})}/>
              <button className="btn" onClick={sendBtc}>Enviar</button>
            </div>
          </Section>

          <Section title="Enviar (Cosmos ATOM)">
            <div className="grid md:grid-cols-4 gap-2">
              <input className="input" placeholder="to cosmos1..." value={cosmos.to} onChange={e=>setCosmos({...cosmos,to:e.target.value})}/>
              <input className="input" placeholder="amount (uatom)" value={cosmos.amount} onChange={e=>setCosmos({...cosmos,amount:e.target.value})}/>
              <div></div>
              <button className="btn" onClick={sendCosmos}>Enviar</button>
            </div>
          </Section>
        </>
      )}

      {res && <div className={"p-3 rounded-lg "+(res.ok? 'bg-[#0e2a18] border border-green-700':'bg-[#2a0e0e] border border-red-700')}>{res.msg}</div>}
    </div>
  )
}
