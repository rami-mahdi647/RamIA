
const { app, BrowserWindow, ipcMain, shell } = require('electron')
const path = require('path')
const fs = require('fs')

// ---- Carga robusta de .env en runtime (Electron) ----
function loadEnv() {
  try {
    const dotenv = require('dotenv')
    const candidates = [
      path.join(process.resourcesPath || '', '.env'),  // app empaquetada
      path.join(__dirname, '..', '.env'),              // dev: ../.env
      path.join(__dirname, '.env'),                    // dev alternativo
      path.join(process.cwd(), '.env'),                // cwd
    ].filter(p => !!p)
    for (const p of candidates) {
      if (fs.existsSync(p)) {
        dotenv.config({ path: p })
        console.log('[QuantumCore] .env cargado desde', p)
        return
      }
    }
    console.warn('[QuantumCore] .env no encontrado; usando process.env del sistema')
  } catch (e) {
    console.warn('[QuantumCore] dotenv no disponible o error cargando .env', e.message)
  }
}
loadEnv()

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

let dag = null; try { dag = require('@stardust-collective/dag4') } catch{}

const SERVICE = 'QuantumCore'
const ACCOUNT = 'default-seed'

function toUint8(arr){ return Uint8Array.from(arr) }
function h160(pub){ return ripemd160(sha256(pub)) }
function btcAddressFromPub(pub){ const words = bech32.toWords(h160(pub)); return bech32.encode('bc', [0, ...words]) }

const PATHS = {
  BTC: (acct=0, i=0)=> `m/84'/0'/${acct}'/0/${i}`,
  EVM: (acct=0, i=0)=> `m/44'/60'/${acct}'/0/${i}`,
  COSMOS: (acct=0, i=0)=> `m/44'/118'/${acct}'/0/${i}`,
  DAG: (acct=0, i=0)=> `m/44'/1137'/${acct}'/0/${i}`
}

// ---- Vault (Keychain) ----
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

// ---- Derivación (solo direcciones) ----
function deriveAllFromSeed(seedBytes, index=0){
  const seed = toUint8(seedBytes)
  const root = HDKey.fromMasterSeed(seed)

  const btcNode = root.derive(PATHS.BTC(0, index))
  const btcAddr = btcNode.publicKey ? btcAddressFromPub(btcNode.publicKey) : '(no pub)'

  const evmNode = root.derive(PATHS.EVM(0, index))
  const evmWallet = evmNode.privateKey ? new ethers.Wallet(evmNode.privateKey) : null

  const cosNode = root.derive(PATHS.COSMOS(0, index))
  let cosmosAddr = '(no pub)'
  if (cosNode.publicKey) {
    const words = bech32.toWords(h160(cosNode.publicKey))
    cosmosAddr = bech32.encode('cosmos', words)
  }

  return [
    { chain:'btc', path: PATHS.BTC(0,index), address: btcAddr, index },
    { chain:'eth', path: PATHS.EVM(0,index), address: evmWallet? evmWallet.address : '(no key)', index },
    { chain:'polygon', path: PATHS.EVM(0,index), address: evmWallet? evmWallet.address : '(no key)', index },
    { chain:'bnb', path: PATHS.EVM(0,index), address: evmWallet? evmWallet.address : '(no key)', index },
    { chain:'cosmos', path: PATHS.COSMOS(0,index), address: cosmosAddr, index },
    { chain:'dag', path: PATHS.DAG(0,index), address: '(dag IPC)', index }
  ]
}

// ---- Envíos (process.env primero; fallback a env recibido del renderer) ----
async function evmSend({ chain, index, to, amount }, env){
  const rpc = (chain==='eth' && process.env.VITE_ETH_RPC)
            || (chain==='polygon' && process.env.VITE_POLYGON_RPC)
            || (chain==='bnb' && process.env.VITE_BNB_RPC)
            || (env && (env.VITE_ETH_RPC || env.VITE_POLYGON_RPC || env.VITE_BNB_RPC))
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

async function btcSend({ index, to, amountSats, feeRate }, env){
  const seed = await vaultGet(); if (!seed) throw new Error('Seed no disponible')
  const node = HDKey.fromMasterSeed(toUint8(seed)).derive(PATHS.BTC(0, index||0))
  if (!node.privateKey || !node.publicKey) throw new Error('Clave no derivada')
  const keyPair = ECPair.fromPrivateKey(Buffer.from(node.privateKey))
  const p2wpkh = bitcoin.payments.p2wpkh({ pubkey: Buffer.from(node.publicKey) })
  const fromAddr = p2wpkh.address

  const api = process.env.VITE_BTC_API || (env && env.VITE_BTC_API) || 'https://mempool.space/api'

  // UTXOs
  const utxos = (await axios.get(`${api}/address/${fromAddr}/utxo`)).data || []
  if (!utxos.length) throw new Error('Sin UTXOs')
  // Select inputs (largest-first)
  utxos.sort((a,b)=>b.value - a.value)
  let selected = [], total = 0
  for (const u of utxos){
    selected.push(u); total += u.value
    const inCount = selected.length
    const outCount = 2
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

async function cosmosSend({ index, to, amountUatom }, env){
  const seed = await vaultGet(); if (!seed) throw new Error('Seed no disponible')
  const node = HDKey.fromMasterSeed(toUint8(seed)).derive(PATHS.COSMOS(0, index||0))
  if (!node.privateKey) throw new Error('Sin privateKey')
  const rpc = process.env.VITE_COSMOS_RPC || (env && env.VITE_COSMOS_RPC)
  if (!rpc) throw new Error('COSMOS RPC no configurado')
  const denom = process.env.VITE_COSMOS_DENOM || (env && env.VITE_COSMOS_DENOM) || 'uatom'

  const wallet = await DirectSecp256k1Wallet.fromKey(Buffer.from(node.privateKey), 'cosmos')
  const [acc] = await wallet.getAccounts()
  const client = await SigningStargateClient.connectWithSigner(rpc, wallet, { gasPrice: GasPrice.fromString('0.025'+denom) })
  const res = await client.sendTokens(acc.address, to, [{ denom, amount: String(amountUatom) }], 'auto')
  return res
}

async function dagInfo(){
  try {
    const node = process.env.VITE_DAG_NODE || 'https://api.constellationnetwork.io'
    const r = await fetch(node).catch(()=>null)
    return { ok: !!(r && r.ok) }
  } catch(e){ return { ok:false, error: String(e) } }
}

// ---- Ventana ----
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

  // Derive
  ipcMain.handle('wallet:derive', async (_e, index)=>{
    const seed = await vaultGet(); if (!seed) throw new Error('Seed no disponible')
    return deriveAllFromSeed(seed, index||0)
  })

  // Enviar
  ipcMain.handle('wallet:evm:send', async (_e, payload, env)=> evmSend(payload, env))
  ipcMain.handle('wallet:btc:send', async (_e, payload, env)=> btcSend(payload, env))
  ipcMain.handle('wallet:cosmos:send', async (_e, payload, env)=> cosmosSend(payload, env))

  // DAG
  ipcMain.handle('wallet:dag:info', async ()=> dagInfo())

  // Log mínimo de presencia de envs
  console.log('[QuantumCore ENV]',
    { ETH: !!process.env.VITE_ETH_RPC, POLYGON: !!process.env.VITE_POLYGON_RPC, BNB: !!process.env.VITE_BNB_RPC,
      COSMOS: !!process.env.VITE_COSMOS_RPC, BTC_API: process.env.VITE_BTC_API, DAG_NODE: process.env.VITE_DAG_NODE })

  createWindow()
})

app.on('window-all-closed', ()=>{ if (process.platform !== 'darwin') app.quit() })
app.on('activate', ()=>{ if (BrowserWindow.getAllWindows().length === 0) createWindow() })
