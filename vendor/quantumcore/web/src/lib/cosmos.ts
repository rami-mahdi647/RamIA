import { SigningStargateClient, StargateClient, GasPrice } from '@cosmjs/stargate'
import { DirectSecp256k1HdWallet } from '@cosmjs/proto-signing'
import { ENV } from './env'

export async function cosmosGetBalance(addr:string){
  const client = await StargateClient.connect(ENV.COSMOS_RPC)
  const bal = await client.getAllBalances(addr)
  return bal
}

// In browser this needs mnemonic; in Electron we prefer IPC to avoid exposing secrets
export async function cosmosSend(mnemonic:string, to:string, amount:string){
  const wallet = await DirectSecp256k1HdWallet.fromMnemonic(mnemonic, { prefix: 'cosmos' })
  const [acc] = await wallet.getAccounts()
  const client = await SigningStargateClient.connectWithSigner(ENV.COSMOS_RPC, wallet, { gasPrice: GasPrice.fromString('0.025uatom') })
  const r = await client.sendTokens(acc.address, to, [{ denom: ENV.COSMOS_DENOM, amount }], 'auto')
  return r
}
