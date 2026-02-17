/**
 * Almacenamiento seguro del seed.
 * - En navegador: AES-GCM (WebCrypto) + PBKDF2 → localStorage
 * - En Electron: IPC hacia keytar (SO keychain)
 */
const VAULT_KEY = 'qc_vault_v1'

function uint8ToB64(u8: Uint8Array){
  return btoa(String.fromCharCode(...u8))
}
function b64ToUint8(b64: string){
  const bin = atob(b64); const arr = new Uint8Array(bin.length)
  for (let i=0;i<bin.length;i++) arr[i] = bin.charCodeAt(i)
  return arr
}

async function deriveKey(pass: string, salt: Uint8Array){
  const enc = new TextEncoder()
  const keyMaterial = await crypto.subtle.importKey('raw', enc.encode(pass), 'PBKDF2', false, ['deriveKey'])
  return crypto.subtle.deriveKey(
    { name:'PBKDF2', salt, iterations: 150000, hash:'SHA-256' },
    keyMaterial,
    { name:'AES-GCM', length: 256 },
    false,
    ['encrypt','decrypt']
  )
}

export async function vaultSave(seed: Uint8Array, passphrase: string){
  // Electron?
  if ((window as any).bridge?.vault?.save) {
    return (window as any).bridge.vault.save(Array.from(seed))
  }
  // Browser
  const salt = crypto.getRandomValues(new Uint8Array(16))
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const key = await deriveKey(passphrase, salt)
  const ct = await crypto.subtle.encrypt({ name:'AES-GCM', iv }, key, seed)
  const payload = { salt: uint8ToB64(salt), iv: uint8ToB64(iv), ct: uint8ToB64(new Uint8Array(ct)) }
  localStorage.setItem(VAULT_KEY, JSON.stringify(payload))
  return true
}

export async function vaultLoad(passphrase?: string): Promise<Uint8Array|null>{
  if ((window as any).bridge?.vault?.get) {
    const data = await (window as any).bridge.vault.get()
    return data ? new Uint8Array(data) : null
  }
  const raw = localStorage.getItem(VAULT_KEY)
  if (!raw) return null
  const payload = JSON.parse(raw)
  const salt = b64ToUint8(payload.salt)
  const iv = b64ToUint8(payload.iv)
  const ct = b64ToUint8(payload.ct)
  const key = await deriveKey(passphrase||'', salt)
  const pt = await crypto.subtle.decrypt({ name:'AES-GCM', iv }, key, ct).catch(()=>null)
  return pt ? new Uint8Array(pt) : null
}

export async function vaultDelete(){
  if ((window as any).bridge?.vault?.del) {
    return (window as any).bridge.vault.del()
  }
  localStorage.removeItem(VAULT_KEY)
  return true
}
