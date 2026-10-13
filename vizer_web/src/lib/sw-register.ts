/** Enregistrement du service worker (PWA installable, design.md §8). */
export function registerServiceWorker(): void {
  if (!('serviceWorker' in navigator)) return;
  // En dev, le SW masquerait les modifications de code : on ne l'active
  // qu'en build.
  if (import.meta.env.DEV) return;

  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register(`${import.meta.env.BASE_URL}sw.js`, {
        scope: import.meta.env.BASE_URL,
      })
      .catch(() => {
        // Pas de SW (contexte non sécurisé, navigation privée) : l'app
        // fonctionne, elle perd seulement le mode hors-ligne complet.
      });
  });
}
