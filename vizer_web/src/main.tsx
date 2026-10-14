import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter } from 'react-router-dom';
import { App } from './App';
import { BankrollProvider } from './context/BankrollContext';
import { DataProvider } from './context/DataContext';
import { LiveProvider } from './context/LiveContext';
import { SettingsProvider } from './context/SettingsContext';
import { ToastProvider } from './context/ToastContext';
import { registerServiceWorker } from './lib/sw-register';
import './styles/tokens.css';
import './styles/base.css';
import './styles/app.css';

const root = document.getElementById('root');
if (!root) throw new Error('#root introuvable');

createRoot(root).render(
  <StrictMode>
    {/* Routing en hash : liens profonds fonctionnels sur GitHub Pages et
        hors-ligne, sans rewrite serveur (cf. vite.config.ts). */}
    <HashRouter>
      <SettingsProvider>
        <ToastProvider>
          <BankrollProvider>
            <DataProvider>
              {/* Le direct dépend du feed du jour : il sait ainsi quand il n'y
                  a rien à suivre et s'abstient de sonder. */}
              <LiveProvider>
                <App />
              </LiveProvider>
            </DataProvider>
          </BankrollProvider>
        </ToastProvider>
      </SettingsProvider>
    </HashRouter>
  </StrictMode>,
);

registerServiceWorker();
