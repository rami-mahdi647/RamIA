import { HDKey } from '@scure/bip32'
import { generateMnemonic, mnemonicToSeedSync, validateMnemonic, wordlist } from '@scure/bip39/spanish'
import { sha256 } from '@noble/hashes/sha256'
import { ripemd160 } from '@noble/hashes/ripemd160'
import { bech32 } from 'bech32'
import { ethers } from 'ethers'
import { toBech32 } from '@cosmjs/encoding'

export type ChainKind = 'btc'|'eth'|'polygon'|'bnb'|'cosmos'|'dag'

export interface DerivedAddr {
  chain: ChainKind
  path: string
  address: string
  index: number
}

export function newMnemonic(words = 12){
  // 12 palabras en español
  return generateMnemonic(wordlist, 128)
}
export function isMnemonicValid(m: string){
  try { return validateMnemonic(m.trim(), wordlist) } catch { return false }
}

export function seedFromMnemonic(m: string){
  return mnemonicToSeedSync(m.normalize('NFKD')) // Buffer
}

export function deriveBTC(seed: Uint8Array, account = 0, index = 0){
  // BIP84 segwit: m/84'/0'/account'/0/index
  const path = `m/84'/0'/${account}'/0/${index}`
  const hd = HDKey.fromMasterSeed(seed).derive(path)
  if (!hd.publicKey) throw new Error('No pubkey')
  const pubkey = hd.publicKey
  const h160 = ripemd160(sha256(pubkey))
  const words = bech32.toWords(h160)
  const addr = bech32.encode('bc', [0, ...words])
  return { chain:'btc', path, address: addr, index } as DerivedAddr
}

export function deriveEVM(seed: Uint8Array, kind:'eth'|'polygon'|'bnb', account = 0, index = 0){
  // BIP44: m/44'/60'/account'/0/index
  const path = `m/44'/60'/${account}'/0/${index}`
  const hd = HDKey.fromMasterSeed(seed).derive(path)
  if (!hd.privateKey) throw new Error('No private key')
  const wallet = new ethers.Wallet(hd.privateKey)
  return { chain: kind, path, address: wallet.address, index } as DerivedAddr
}

export function deriveCosmos(seed: Uint8Array, account = 0, index = 0){
  // BIP44: m/44'/118'/account'/0/index
  const path = `m/44'/118'/${account}'/0/${index}`
  const hd = HDKey.fromMasterSeed(seed).derive(path)
  if (!hd.publicKey) throw new Error('No pubkey')
  const pub = hd.publicKey
  const addr = toBech32('cosmos', ripemd160(sha256(pub)))
  return { chain:'cosmos', path, address: addr, index } as DerivedAddr
}

// DAG: para derivación completa usa dag4 en Electron (IPC). Aquí solo devolvemos placeholder.
export function deriveDAGPlaceholder(index = 0){
  return { chain:'dag', path:`m/44'/1137'/0'/0/${index}`, address: '(usar Electron IPC dag4)', index } as DerivedAddr
}

export function deriveAll(seed: Uint8Array, index = 0){
  return [
    deriveBTC(seed, 0, index),
    deriveEVM(seed, 'eth', 0, index),
    deriveEVM(seed, 'polygon', 0, index),
    deriveEVM(seed, 'bnb', 0, index),
    deriveCosmos(seed, 0, index),
    deriveDAGPlaceholder(index)
  ]
}
