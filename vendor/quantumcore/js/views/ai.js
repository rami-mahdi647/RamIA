Router.use('/ai', {
  title: 'AI-as-a-Service',
  actionsHTML: ``,
  render: async () => { 
return `
  <div class="badge">AI‑as‑a‑Service</div>
  <p>Expone endpoints para tus agentes (QNN/LLM). Integra tu backend en <code>/backend</code>.</p>
  <ul>
    <li><b>Pattern Miner</b>: QNN 32 capas (stub, conectar runtime).</li>
    <li><b>Sentiment</b>: inferencia ligera (stub).</li>
    <li><b>Reranker</b>: latencia baja (stub).</li>
  </ul>
`; },
  afterRender: async () => {  }
});
