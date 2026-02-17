(() => {
  const banner = document.getElementById('updateBanner');
  const button = document.getElementById('updateBtn');
  if (!('serviceWorker' in navigator)) return;

  const showBanner = () => {
    if (banner) banner.style.display = 'block';
  };

  navigator.serviceWorker.register('/sw.js').then((registration) => {
    if (registration.waiting) showBanner();

    registration.addEventListener('updatefound', () => {
      const newWorker = registration.installing;
      if (!newWorker) return;
      newWorker.addEventListener('statechange', () => {
        if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
          showBanner();
        }
      });
    });

    if (button) {
      button.addEventListener('click', () => {
        if (registration.waiting) {
          registration.waiting.postMessage({ type: 'SKIP_WAITING' });
        } else {
          window.location.reload();
        }
      });
    }

    navigator.serviceWorker.addEventListener('controllerchange', () => {
      window.location.reload();
    });

    setInterval(() => registration.update().catch(() => {}), 60000);
  }).catch(() => {});
})();
