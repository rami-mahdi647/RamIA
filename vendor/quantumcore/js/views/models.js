Router.use('/models', {
  title: 'Model Lab',
  actionsHTML: ``,
  render: async () => { 
return `
  <div class="badge">Model Lab</div>
  <p>Gestión de modelos (32 QNNs, versiones, métricas). UI placeholder.</p>
  <table class="table">
    <tr><th>Modelo</th><th>Versión</th><th>p95</th><th>Coste/1k</th><th>Groundedness</th></tr>
    ${Array.from({length:8}).map((_,i)=>`<tr><td>QNN-${i+1}</td><td>v1.0</td><td>150ms</td><td>€0.04</td><td>0.92</td></tr>`).join('')}
  </table>
`; },
  afterRender: async () => {  }
});
