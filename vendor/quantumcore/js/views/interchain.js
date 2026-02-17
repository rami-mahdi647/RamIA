Router.use('/interchain', {
  title: 'Interchain Router',
  actionsHTML: ``,
  render: async () => { 
return `
  <div class="badge">Router</div>
  <p>Puentes soportados: BTC • Ethereum • Polygon • BNB • Cosmos • DAG (UI placeholder).</p>
  <div class="kpis">
    <div class="kpi"><b>Network</b><span>BTC (live)</span></div>
    <div class="kpi"><b>ETH</b><span>stub</span></div>
    <div class="kpi"><b>Polygon</b><span>stub</span></div>
    <div class="kpi"><b>BNB</b><span>stub</span></div>
  </div>
`; },
  afterRender: async () => {  }
});
