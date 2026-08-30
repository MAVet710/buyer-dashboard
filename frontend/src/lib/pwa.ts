export async function registerDoobieLogicServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (!("serviceWorker" in navigator)) return null;
  if (window.location.protocol !== "https:" && window.location.hostname !== "localhost") return null;
  try {
    return await navigator.serviceWorker.register("/service-worker.js", { scope: "/" });
  } catch (error) {
    console.warn("DoobieLogic service worker registration failed", error);
    return null;
  }
}
