const Router = {
  current: null,
  routes: {},
  init() {
    window.addEventListener('hashchange', () => this.render());
    this.render();
  },
  use(path, view) { this.routes[path] = view; },
  setActive(path) {
    const a = document.querySelectorAll('.nav-item');
    a.forEach(x => x.classList.toggle('active', x.getAttribute('href') === '#'+path));
    document.getElementById('title').textContent = (this.routes[path]?.title || 'QuantumCore');
    document.getElementById('actions').innerHTML = this.routes[path]?.actionsHTML || '';
  },
  async render() {
    const hash = location.hash || '#/dashboard';
    const path = hash.substring(1);
    const view = this.routes[path] || this.routes['/dashboard'];
    this.setActive(path);
    const container = document.getElementById('view');
    container.innerHTML = await view.render();
    view.afterRender?.();
  }
};