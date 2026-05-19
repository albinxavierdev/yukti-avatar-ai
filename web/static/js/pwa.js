/**
 * PWA: service worker registration + optional install prompt.
 */
(function () {
  if (!("serviceWorker" in navigator)) return;

  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/sw.js", { scope: "/" })
      .catch((e) => console.warn("SW register:", e));
  });

  let deferredInstall;
  const installBanner = document.getElementById("pwaInstallBanner");
  const installBtn = document.getElementById("pwaInstallBtn");
  const installDismiss = document.getElementById("pwaInstallDismiss");

  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferredInstall = e;
    if (installBanner && !window.matchMedia("(display-mode: standalone)").matches) {
      installBanner.hidden = false;
    }
  });

  installBtn?.addEventListener("click", async () => {
    if (!deferredInstall) return;
    deferredInstall.prompt();
    await deferredInstall.userChoice;
    deferredInstall = null;
    if (installBanner) installBanner.hidden = true;
  });

  installDismiss?.addEventListener("click", () => {
    if (installBanner) installBanner.hidden = true;
    deferredInstall = null;
  });

  window.addEventListener("appinstalled", () => {
    if (installBanner) installBanner.hidden = true;
    deferredInstall = null;
  });
})();
