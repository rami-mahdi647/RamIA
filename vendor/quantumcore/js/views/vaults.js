Router.use('/vaults', {
  title: 'Vaults & Minería',
  actionsHTML: ``,
  render: async () => { 
return `
  <div class="kpis">
    <div class="kpi"><b>Dificultad (ajuste)</b><span id="vm-diff">—</span></div>
    <div class="kpi"><b>Promedio 24h (tx)</b><span id="vm-tx">—</span></div>
    <div class="kpi"><b>Mempool</b><span id="vm-mc">—</span></div>
    <div class="kpi"><b>Tamaño</b><span id="vm-size">— vMB</span></div>
  </div>
  <hr class="sep"/>
  <div class="panel">
    <div class="panel-title">Últimos bloques</div>
    <ul class="blocks" id="vm-blocks"></ul>
  </div>
`; },
  afterRender: async () => { 
(async()=>{
  try{
    const d = await safeFetchJSON(API.difficulty());
    document.getElementById('vm-diff').textContent = (d.adjustment_percent??0).toFixed(2)+'%';
  }catch(e){}
  try{
    const m = await safeFetchJSON(API.mempool());
    document.getElementById('vm-mc').textContent = fmt(m.count||0);
    document.getElementById('vm-size').textContent = ((m.vsize||0)/1e6).toFixed(2);
  }catch(e){}
  try{
    const bs = await safeFetchJSON(API.blocks());
    const avgTx = Math.round((bs||[]).slice(0,6).reduce((s,b)=>s+(b.tx_count||0),0)/Math.max(1,Math.min(6,(bs||[]).length)));
    document.getElementById('vm-tx').textContent = fmt(avgTx);
    const list = document.getElementById('vm-blocks'); list.innerHTML='';
    (bs||[]).slice(0,8).forEach(b=>{
      const li=document.createElement('li'); li.className='block';
      const t = new Date((b.timestamp||0)*1000).toLocaleString();
      li.innerHTML = `<b>#${b.height}</b><br><small>${t}</small><br><small>TX: ${fmt(b.tx_count||0)}</small>`;
      list.appendChild(li);
    });
  }catch(e){}
})();
 }
});
