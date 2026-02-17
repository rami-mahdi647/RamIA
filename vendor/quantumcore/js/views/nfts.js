Router.use('/nfts', {
  title: 'NFTs',
  actionsHTML: ``,
  render: async () => { 
return `
  <div class="badge">NFTs</div>
  <p>Quantum Badges (funcionales). Conecta contrato para listar y mintear.</p>
  <div class="kpis">
    <div class="kpi"><b>Badges activos</b><span>—</span></div>
    <div class="kpi"><b>Yield</b><span>—</span></div>
    <div class="kpi"><b>Holders</b><span>—</span></div>
    <div class="kpi"><b>Royalties</b><span>—</span></div>
  </div>
`; },
  afterRender: async () => {  }
});
