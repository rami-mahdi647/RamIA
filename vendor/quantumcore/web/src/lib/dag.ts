export async function dagPing(node:string){
  const r = await fetch(node, { method: 'GET' }).catch(()=>null)
  return r?.ok || false
}
