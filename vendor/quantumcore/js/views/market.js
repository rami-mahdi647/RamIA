Router.use('/market', {
  title: 'Market Sentinel',
  actionsHTML: ``,
  render: async () => { 
return `
  <div class="badge">Market Sentinel</div>
  <p>Feed de tendencias, PRs, costes y frustración de usuarios (conecta tus fuentes).</p>
  <ul class="signals" id="mk-feed">
    <li class="signal"><i></i><b>Inicializando</b><span>Conecta fuentes externas (GTrends, GitHub PRs, tickets)</span></li>
  </ul>
`; },
  afterRender: async () => {  }
});
