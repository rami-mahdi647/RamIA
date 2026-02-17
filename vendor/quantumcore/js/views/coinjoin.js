Router.use('/coinjoin', {
  title: 'CoinJoin',
  actionsHTML: ``,
  render: async () => { 
return `
  <div class="badge">UI CoinJoin</div>
  <p>Interfaz de mezcla UTXO (no operativa por defecto). Permite conectar un coordinador externo compatible.<br>
  <small>Requiere módulo externo y cumplimiento legal según jurisdicción.</small></p>
  <div class="kpis">
    <div class="kpi"><b>Estado</b><span>Desconectado</span></div>
    <div class="kpi"><b>Coordinadores</b><span>0</span></div>
    <div class="kpi"><b>Round min</b><span>—</span></div>
    <div class="kpi"><b>Tarifa</b><span>—</span></div>
  </div>
`; },
  afterRender: async () => {  }
});
