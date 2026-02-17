Router.use('/settings', {
  title: 'Settings',
  actionsHTML: ``,
  render: async () => { 
return `
  <div class="badge">Settings</div>
  <div class="addr-label">
    <span>BTC Address</span>
    <input id="s-addr" placeholder="bc1..." />
    <button id="s-save">Guardar</button>
  </div>
  <p><small>Se guarda localmente en tu navegador/app.</small></p>
`; },
  afterRender: async () => { 
const saddr = document.getElementById('s-addr');
saddr.value = localStorage.getItem('qc_btc_addr')||'';
document.getElementById('s-save').onclick = ()=>{
  const v = saddr.value.trim(); if(!v) return;
  localStorage.setItem('qc_btc_addr', v);
  alert('Guardado'); location.hash = '#/wallet';
};
 }
});
