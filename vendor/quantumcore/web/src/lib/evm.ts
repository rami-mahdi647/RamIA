import { BrowserProvider, JsonRpcProvider, Wallet, formatEther, parseEther } from 'ethers'
import { ENV } from './env'

export function getEvmProvider(kind:'eth'|'polygon'|'bnb'){
  const url = kind==='eth' ? ENV.ETH_RPC : kind==='polygon' ? ENV.POLYGON_RPC : ENV.BNB_RPC
  return new JsonRpcProvider(url)
}

export async function evmGetBalance(address:string, kind:'eth'|'polygon'|'bnb'){
  const p = getEvmProvider(kind)
  const b = await p.getBalance(address)
  return Number(formatEther(b))
}

// Sign & send (browser) - user pastes private key (NOT stored). In Electron prefer IPC.
export async function evmSendTx(pk:string, to:string, amountEth:string, kind:'eth'|'polygon'|'bnb'){
  const provider = getEvmProvider(kind)
  const wallet = new Wallet(pk, provider)
  const tx = await wallet.sendTransaction({ to, value: parseEther(amountEth) })
  return await tx.wait()
}
