Router.use('/dashboard', {
  title: 'Dashboard',
  actionsHTML: `<label class="addr-label">
<span>BTC:</span><input id="addrIn" placeholder="bc1..." />
<button id="addrBtn">Guardar</button>
</label>`,
  render: async () => { 
let html = `
  <section class="cards">
    <div class="card"><div class="card-title">Saldo BTC</div>
      <div class="card-value"><span id="d-balance">—</span> <small>BTC</small></div>
      <div class="card-sub" id="d-unconf">Pendiente: — sats</div>
    </div>
    <div class="card"><div class="card-title">Mempool</div>
      <div class="card-value"><span id="d-mcount">—</span> tx</div>
      <div class="card-sub">Tamaño: <span id="d-mvsize">—</span> vMB</div>
    </div>
    <div class="card"><div class="card-title">Tarifas</div>
      <div class="fees">
        <div><b>Lento</b><span id="d-fee-low">—</span> sat/vB</div>
        <div><b>Medio</b><span id="d-fee-mid">—</span> sat/vB</div>
        <div><b>Rápido</b><span id="d-fee-high">—</span> sat/vB</div>
      </div>
      <div class="card-sub">Fuente: mempool.space</div>
    </div>
  </section>
  <section class="grid">
    <div class="panel">
      <div class="panel-title">Últimos bloques</div>
      <ul class="blocks" id="d-blocks"></ul>
    </div>
    <div class="panel">
      <div class="panel-title">Señales</div>
      <div class="signals" id="d-signals"></div>
    </div>
  </section>`;
return html;
 },
  afterRender: async () => { 
(async () => {
  // Address from localStorage if exists
  const addr = localStorage.getItem('qc_btc_addr');
  if (addr) {
    try {
      const s = await getAddressSummary(addr);
      document.getElementById('d-balance').textContent = satsToBTC(s.confirmed);
      document.getElementById('d-unconf').textContent = `Pendiente: ${fmt(s.unconf)} sats`;
    } catch {}
  }
  try {
    const m = await safeFetchJSON(API.mempool());
    document.getElementById('d-mcount').textContent = fmt(m.count||0);
    document.getElementById('d-mvsize').textContent = ((m.vsize||0)/1e6).toFixed(2);
    const f = await safeFetchJSON(API.fees());
    document.getElementById('d-fee-low').textContent = fmt(f.hourFee||f.minimumFee||1);
    document.getElementById('d-fee-mid').textContent = fmt(f.halfHourFee||f.minimumFee||2);
    document.getElementById('d-fee-high').textContent = fmt(f.fastestFee||f.minimumFee||3);
    const bs = await safeFetchJSON(API.blocks());
    const list = document.getElementById('d-blocks'); list.innerHTML = '';
    (bs||[]).slice(0,8).forEach(b => {
      const t = new Date((b.timestamp||0)*1000).toLocaleString();
      const li = document.createElement('li'); li.className='block';
      li.innerHTML = `<b>#${b.height}</b><br><small>${t}</small><br><small>TX: ${fmt(b.tx_count||0)}</small>`;
      list.appendChild(li);
    });
    const sig = document.getElementById('d-signals');
    const srow = (t,m)=>{const r=document.createElement('div');r.className='signal';r.innerHTML=`<i></i><b>${t}</b><span>${m}</span>`;sig.prepend(r); while(sig.children.length>8) sig.removeChild(sig.lastChild);};
    srow('On‑chain', 'Datos actualizados correctamente.');
  } catch(e) {}
})();

const btn = document.getElementById('addrBtn');
if (btn) btn.onclick = ()=>{
  const v = document.getElementById('addrIn').value.trim();
  if (v){ localStorage.setItem('qc_btc_addr', v); location.hash='#/wallet'; }
};
 }
});
