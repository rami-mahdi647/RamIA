Router.use('/subscriptions', {
  title: 'Subscriptions',
  actionsHTML: ``,
  render: async () => { 
return `
  <div class="badge">Subscriptions</div>
  <p>Pagos recurrentes y planes (placeholder). Integra tu pasarela en backend.</p>
  <ul>
    <li>Starter — €9.90/mes</li>
    <li>Pro — €29.00/mes</li>
    <li>Enterprise — a medida</li>
  </ul>
`; },
  afterRender: async () => {  }
});
