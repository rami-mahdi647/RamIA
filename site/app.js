(() => {
  const updateBanner = document.getElementById("updateBanner");
  const updateBtn = document.getElementById("updateBtn");

  function showUpdate() {
    if (updateBanner) updateBanner.style.display = "block";
  }

  if (!("serviceWorker" in navigator)) return;

  navigator.serviceWorker.register("/sw.js").then((reg) => {
    if (reg.waiting) showUpdate();

    reg.addEventListener("updatefound", () => {
      const worker = reg.installing;
      if (!worker) return;
      worker.addEventListener("statechange", () => {
        if (worker.state === "installed" && navigator.serviceWorker.controller) {
          showUpdate();
        }
      });
    });

    navigator.serviceWorker.addEventListener("controllerchange", () => {
      window.location.reload();
    });

    if (updateBtn) {
      updateBtn.addEventListener("click", () => {
        if (reg.waiting) reg.waiting.postMessage({ type: "SKIP_WAITING" });
      });
    }

    setInterval(() => reg.update().catch(() => {}), 60 * 1000);
  }).catch(() => {});
})();
