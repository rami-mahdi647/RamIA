Router.use('/dao', {
  title: 'DAO',
  actionsHTML: ``,
  render: async () => { 
return `
  <div class="badge">DAO</div>
  <p>Propuestas, votos y quorum. Conecta tu backend/contratos para activar.</p>
  <table class="table">
    <tr><th>ID</th><th>Título</th><th>Estado</th><th>Fin votación</th></tr>
    <tr><td>#12</td><td>Migrar a modelo QNN v2</td><td>Abierto</td><td>2025-09-10</td></tr>
    <tr><td>#11</td><td>Optimizar fees Interchain</td><td>Completado</td><td>2025-08-02</td></tr>
  </table>
`; },
  afterRender: async () => {  }
});
