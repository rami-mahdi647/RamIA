Router.use('/wallet', {
  title: 'Wallet',
  actionsHTML: ``,
  render: async () => { 
const addr = localStorage.getItem('qc_btc_addr') || '';
let html = `
  <div class="kpis">
    <div class="kpi"><b>Dirección</b><span>${addr?addr:'(no configurada)'}</span></div>
    <div class="kpi"><b>Saldo</b><span id="w-bal">— BTC</span></div>
    <div class="kpi"><b>Pendiente</b><span id="w-pend">— sats</span></div>
    <div class="kpi"><b>TX totales</b><span id="w-txs">—</span></div>
  </div>
  <hr class="sep"/>
  <div class="badge">Pega tu dirección BTC en Settings o en Dashboard ▶ Wallet</div>
`; return html;
 },
  afterRender: async () => { 
(async()=>{
  const addr = localStorage.getItem('qc_btc_addr');
  if (!addr) return;
  try {
    const s = await getAddressSummary(addr);
    document.getElementById('w-bal').textContent = satsToBTC(s.confirmed)+' BTC';
    document.getElementById('w-pend').textContent = fmt(s.unconf)+' sats';
    document.getElementById('w-txs').textContent = fmt(s.tx_count);
  } catch(e){}
})();
 }
});
