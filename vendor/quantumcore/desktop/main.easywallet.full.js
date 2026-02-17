
const { app, BrowserWindow, ipcMain, shell } = require('electron')
const path = require('path')
const keytar = require('keytar')
const axios = require('axios')

const { HDKey } = require('@scure/bip32')
const { bech32 } = require('bech32')
const { sha256 } = require('@noble/hashes/sha256')
const { ripemd160 } = require('@noble/hashes/ripemd160')

const ecc = require('tiny-secp256k1')
const bitcoin = require('bitcoinjs-lib')
const ECPairFactory = require('ecpair').ECPairFactory
const ECPair = ECPairFactory(ecc)

const { ethers } = require('ethers')
const { DirectSecp256k1Wallet } = require('@cosmjs/proto-signing')
const { SigningStargateClient, GasPrice } = require('@cosmjs/stargate')

// If using dag4:
let dag = null; try { dag = require('@stardust-collective/dag4') } catch{}

const SERVICE = 'QuantumCore'
const ACCOUNT = 'default-seed'

// Helpers
function toUint8(arr){ return Uint8Array.from(arr) }
function h160(pub){ return ripemd160(sha256(pub)) }
function btcAddressFromPub(pub){ const words = bech32.toWords(h160(pub)); return bech32.encode('bc', [0, ...words]) }

// Derivation paths
const PATHS = {
  BTC: (acct=0, i=0)=> `m/84'/0'/${acct}'/0/${i}`,           // BIP84 P2WPKH
  EVM: (acct=0, i=0)=> `m/44'/60'/${acct}'/0/${i}`,           // BIP44 60
  COSMOS: (acct=0, i=0)=> `m/44'/118'/${acct}'/0/${i}`,       // BIP44 118
  DAG: (acct=0, i=0)=> `m/44'/1137'/${acct}'/0/${i}`          // heuristic
}

// Keychain vault
async function vaultSave(bytes){
  const b64 = Buffer.from(Uint8Array.from(bytes)).toString('base64')
  await keytar.setPassword(SERVICE, ACCOUNT, b64)
  return true
}
async function vaultGet(){
  const b64 = await keytar.getPassword(SERVICE, ACCOUNT)
  if (!b64) return null
  const buf = Buffer.from(b64, 'base64')
  return Array.from(buf)
}
async function vaultDel(){
  await keytar.deletePassword(SERVICE, ACCOUNT)
  return true
}

// Derive addresses without exposing seed
function deriveAllFromSeed(seedBytes, index=0){
  const seed = toUint8(seedBytes)
  const root = HDKey.fromMasterSeed(seed)

  // BTC (p2wpkh)
  const btcNode = root.derive(PATHS.BTC(0, index))
  const btcAddr = btcNode.publicKey ? btcAddressFromPub(btcNode.publicKey) : '(no pub)'
  // EVM
  const evmNode = root.derive(PATHS.EVM(0, index))
  const evmWallet = evmNode.privateKey ? new ethers.Wallet(evmNode.privateKey) : null
  // Cosmos
  const cosNode = root.derive(PATHS.COSMOS(0, index))
  let cosmosAddr = '(no pub)'
  if (cosNode.publicKey) {
    const pub = cosNode.publicKey
    const words = bech32.toWords(h160(pub))
    cosmosAddr = bech32.encode('cosmos', words)
  }
  // DAG
  let dagAddr = '(dag IPC)'

  return [
    { chain:'btc', path: PATHS.BTC(0,index), address: btcAddr, index },
    { chain:'eth', path: PATHS.EVM(0,index), address: evmWallet? evmWallet.address : '(no key)', index },
    { chain:'polygon', path: PATHS.EVM(0,index), address: evmWallet? evmWallet.address : '(no key)', index },
    { chain:'bnb', path: PATHS.EVM(0,index), address: evmWallet? evmWallet.address : '(no key)', index },
    { chain:'cosmos', path: PATHS.COSMOS(0,index), address: cosmosAddr, index },
    { chain:'dag', path: PATHS.DAG(0,index), address: dagAddr, index }
  ]
}

// EVM send
async function evmSend({ chain, index, to, amount }, env){
  const rpc = chain==='eth' ? env.VITE_ETH_RPC : chain==='polygon' ? env.VITE_POLYGON_RPC : env.VITE_BNB_RPC
  if (!rpc) throw new Error('RPC no configurado')
  const seed = await vaultGet(); if (!seed) throw new Error('Seed no disponible')
  const node = HDKey.fromMasterSeed(toUint8(seed)).derive(PATHS.EVM(0, index||0))
  if (!node.privateKey) throw new Error('Sin privateKey')
  const provider = new ethers.JsonRpcProvider(rpc)
  const wallet = new ethers.Wallet(node.privateKey, provider)
  const tx = await wallet.sendTransaction({ to, value: ethers.parseEther(String(amount)) })
  const receipt = await tx.wait()
  return { hash: tx.hash, receipt }
}

// BTC send (simple P2WPKH): amount in sats, feeRate sat/vB
async function btcSend({ index, to, amountSats, feeRate }, env){
  const seed = await vaultGet(); if (!seed) throw new Error('Seed no disponible')
  const node = HDKey.fromMasterSeed(toUint8(seed)).derive(PATHS.BTC(0, index||0))
  if (!node.privateKey || !node.publicKey) throw new Error('Clave no derivada')
  const keyPair = ECPair.fromPrivateKey(Buffer.from(node.privateKey))
  const p2wpkh = bitcoin.payments.p2wpkh({ pubkey: Buffer.from(node.publicKey) })
  const fromAddr = p2wpkh.address

  const api = process.env.VITE_BTC_API || 'https://mempool.space/api'
  // UTXOs
  const utxos = (await axios.get(`${api}/address/${fromAddr}/utxo`)).data || []
  if (!utxos.length) throw new Error('Sin UTXOs')
  // Select inputs (largest-first)
  utxos.sort((a,b)=>b.value - a.value)
  let selected = [], total = 0
  for (const u of utxos){
    selected.push(u); total += u.value
    // rough vbytes estimate: 10 + in*68 + out*31
    const inCount = selected.length
    const outCount = 2 // to + change
    const vbytes = 10 + inCount*68 + outCount*31
    const fee = Math.ceil(vbytes * (feeRate||15))
    if (total >= (amountSats + fee)) break
  }
  if (total < amountSats) throw new Error('Fondos insuficientes')
  const inCount = selected.length
  const outCount = 2
  const vbytes = 10 + inCount*68 + outCount*31
  const fee = Math.ceil(vbytes * (feeRate||15))
  const change = total - amountSats - fee
  if (change < 0) throw new Error('Fondos insuficientes (fee)')

  const psbt = new bitcoin.Psbt({ network: bitcoin.networks.bitcoin })
  for (const u of selected){
    // fetch full tx to get nonWitnessUtxo or use witnessUtxo (faster)
    const tx = (await axios.get(`${api}/tx/${u.txid}/hex`)).data
    psbt.addInput({
      hash: u.txid,
      index: u.vout,
      nonWitnessUtxo: Buffer.from(tx, 'hex')
    })
  }
  psbt.addOutput({ address: to, value: amountSats })
  if (change > 546) psbt.addOutput({ address: fromAddr, value: change })

  selected.forEach((_, idx)=> psbt.signInput(idx, keyPair) )
  psbt.finalizeAllInputs()
  const raw = psbt.extractTransaction().toHex()
  const txid = (await axios.post(`${api}/tx`, raw, { headers: {'Content-Type':'text/plain'} })).data
  return { txid, fee }
}

// Cosmos send (uatom)
async function cosmosSend({ index, to, amountUatom }, env){
  const seed = await vaultGet(); if (!seed) throw new Error('Seed no disponible')
  const node = HDKey.fromMasterSeed(toUint8(seed)).derive(PATHS.COSMOS(0, index||0))
  if (!node.privateKey) throw new Error('Sin privateKey')
  const rpc = env.VITE_COSMOS_RPC; if (!rpc) throw new Error('COSMOS RPC no configurado')
  const denom = env.VITE_COSMOS_DENOM || 'uatom'

  const wallet = await DirectSecp256k1Wallet.fromKey(Buffer.from(node.privateKey), 'cosmos')
  const [acc] = await wallet.getAccounts()
  const client = await SigningStargateClient.connectWithSigner(rpc, wallet, { gasPrice: GasPrice.fromString('0.025'+denom) })
  const res = await client.sendTokens(acc.address, to, [{ denom, amount: String(amountUatom) }], 'auto')
  return res
}

// DAG (placeholder IPC using dag4)
async function dagInfo(){
  if (!dag) return { ok:false, error:'dag4 no disponible' }
  try {
    const node = process.env.VITE_DAG_NODE || 'https://api.constellationnetwork.io'
    const resp = await fetch(node).catch(()=>null)
    return { ok: !!(resp && resp.ok) }
  } catch(e){ return { ok:false, error: String(e) } }
}

function createWindow(){
  const win = new BrowserWindow({
    width: 1280, height: 860,
    webPreferences: { preload: path.join(__dirname, 'preload.easywallet.full.js'), contextIsolation: true, nodeIntegration: false, sandbox: true }
  })
  win.loadFile(path.join(__dirname, 'app', 'index.html'))
  win.webContents.setWindowOpenHandler(({url}) => { shell.openExternal(url); return { action: 'deny' } })
}

app.whenReady().then(()=>{
  // Vault
  ipcMain.handle('vault:save', async (_e, bytes)=> vaultSave(bytes))
  ipcMain.handle('vault:get', async (_e)=> vaultGet())
  ipcMain.handle('vault:del', async (_e)=> vaultDel())

  // Derive (addresses only)
  ipcMain.handle('wallet:derive', async (_e, index)=>{
    const seed = await vaultGet(); if (!seed) throw new Error('Seed no disponible')
    return deriveAllFromSeed(seed, index||0)
  })

  // EVM/BTC/Cosmos send
  ipcMain.handle('wallet:evm:send', async (_e, payload, env)=> evmSend(payload, env))
  ipcMain.handle('wallet:btc:send', async (_e, payload, env)=> btcSend(payload, env))
  ipcMain.handle('wallet:cosmos:send', async (_e, payload, env)=> cosmosSend(payload, env))

  // DAG info
  ipcMain.handle('wallet:dag:info', async ()=> dagInfo())

  createWindow()
})

app.on('window-all-closed', ()=>{ if (process.platform !== 'darwin') app.quit() })
app.on('activate', ()=>{ if (BrowserWindow.getAllWindows().length === 0) createWindow() })
