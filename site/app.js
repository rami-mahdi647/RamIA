(async () => {
  const btn = document.getElementById("updateBtn");

  if ("serviceWorker" in navigator) {
    const reg = await navigator.serviceWorker.register("/sw.js");

    // Si hay update esperando, avisa
    if (reg.waiting) {
      btn.style.display = "inline-block";
    }

    reg.addEventListener("updatefound", () => {
      const sw = reg.installing;
      if (!sw) return;
      sw.addEventListener("statechange", () => {
        if (sw.state === "installed" && navigator.serviceWorker.controller) {
          btn.style.display = "inline-block";
        }
      });
    });

    btn.addEventListener("click", async () => {
      if (reg.waiting) {
        reg.waiting.postMessage({ type: "SKIP_WAITING" });
      }
      location.reload();
    });

    navigator.serviceWorker.addEventListener("message", (event) => {
      if (event.data?.type === "RELOAD") location.reload();
    });
  }
})();
