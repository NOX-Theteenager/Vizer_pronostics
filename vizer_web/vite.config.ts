import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Base relative : la PWA fonctionne telle quelle sur GitHub Pages
// (/Vizer_pronostics/), sur un domaine racine, ou servie depuis un
// sous-dossier quelconque. Le routing est en hash pour la même raison :
// pas de rewrite serveur à configurer, et les liens profonds marchent
// hors-ligne quand le service worker sert le shell.
export default defineConfig({
  base: './',
  plugins: [react()],
  server: { port: 5173, host: true },
  build: {
    target: 'es2022',
    outDir: 'dist',
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
        },
      },
    },
  },
});
