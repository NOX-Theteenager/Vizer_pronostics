/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Racine des prédictions publiées (branche models-artifacts). */
  readonly VITE_DATA_BASE?: string;
  /** '1' pour lire les échantillons de public/mock/ au lieu du réseau. */
  readonly VITE_USE_MOCK?: string;
  /** Dépôt interrogé par l'écran Admin (runs GitHub Actions). */
  readonly VITE_GITHUB_REPO?: string;
  /** Force l'adresse du relais de scores en direct (dev local). */
  readonly VITE_LIVE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
