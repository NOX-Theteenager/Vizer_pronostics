import { useCallback, useEffect, useState } from 'react';
import { IconArrowDown, IconArrowUp, IconCheck, IconChevronRight, IconDownload, IconWarning, IconX } from '../components/Icons';
import { SegButton, SegGroup, SectionLabel, Switch } from '../components/Primitives';
import {
  applyBackup,
  backupFilename,
  collectBackup,
  parseBackup,
  summarize,
  type BackupSummary,
} from '../lib/backup';
import { pushStatus, subscribePush, unsubscribePush, type PushStatus } from '../lib/push';
import {
  ensureSyncKey,
  isValidKey,
  pullState,
  pushState,
  readSyncKey,
  SYNC_AVAILABLE,
  writeSyncKey,
} from '../lib/sync';
import { useToast } from '../context/ToastContext';
import { AmountSheet } from '../components/overlays/AmountSheet';
import { useBankroll } from '../context/BankrollContext';
import { useData } from '../context/DataContext';
import { useSettings } from '../context/SettingsContext';
import { QUIET_END, QUIET_START, useAlerts } from '../hooks/useAlerts';
import { DATA_BASE } from '../lib/api';
import { CURRENCIES, CURRENCY_CODES, formatMoney, formatPnl, type CurrencyCode } from '../lib/currency';
import { KELLY_CAP, KELLY_FRACTIONS, KELLY_HINT, KELLY_LABEL } from '../lib/kelly';
import { formatShortDate, timeAgo } from '../lib/format';
import type { ProbFormat, ThemeMode } from '../lib/settings';
import { clearDataCache, downloadText } from '../lib/storage';
import { SPORTS, type Sport } from '../types/model';
import { Link } from 'react-router-dom';

/** Écran Réglages — stockage local uniquement. */
export function Settings({
  onOpenAlerts,
  onOpenNotif,
  onOpenPermission,
  onOpenInstall,
  onReplayOnboarding,
}: {
  onOpenAlerts: () => void;
  onOpenNotif: () => void;
  onOpenPermission: () => void;
  onOpenInstall: () => void;
  onReplayOnboarding: () => void;
}) {

  const { settings, update } = useSettings();
  const { generatedAt, origin, refresh, loadDemo } = useData();
  const { permission } = useAlerts();
  const { bankroll, transactions, deposit, withdraw } = useBankroll();
  const [sheet, setSheet] = useState<'deposit' | 'withdraw' | null>(null);
  const [cacheCleared, setCacheCleared] = useState(false);
  const { showToast } = useToast();

  /**
   * Notifications hors application.
   *
   * Distinct de `alertsEnabled`, qui ne gouverne que les alertes affichées
   * quand l'app est ouverte : ici le serveur pousse, donc l'abonnement vit
   * côté serveur et doit être interrogé plutôt que déduit d'un réglage local.
   */
  const [push, setPush] = useState<PushStatus | null>(null);
  const [pushBusy, setPushBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    void pushStatus().then((st) => alive && setPush(st));
    return () => {
      alive = false;
    };
  }, []);

  const togglePush = useCallback(
    async (wanted: boolean) => {
      setPushBusy(true);
      const error = wanted ? await subscribePush(settings.alertThreshold) : await unsubscribePush();
      showToast(
        error ??
          (wanted
            ? 'Notifications activées — même app fermée'
            : 'Notifications désactivées'),
      );
      setPush(await pushStatus());
      setPushBusy(false);
    },
    [settings.alertThreshold, showToast],
  );

  /* ── Sauvegarde et synchronisation ─────────────────────────────────── */

  const [syncKey, setSyncKey] = useState<string | null>(() => readSyncKey());
  const [keyDraft, setKeyDraft] = useState('');
  const [keyVisible, setKeyVisible] = useState(false);
  const [syncBusy, setSyncBusy] = useState(false);
  /** Sauvegarde distante trouvée, en attente d'une décision explicite. */
  const [incoming, setIncoming] = useState<
    { summary: BackupSummary; apply: () => void } | null
  >(null);

  const exportBackup = useCallback(() => {
    const payload = JSON.stringify(collectBackup(), null, 2);
    showToast(
      downloadText(backupFilename(), payload, 'application/json')
        ? 'Sauvegarde téléchargée'
        : 'Téléchargement indisponible',
    );
  }, [showToast]);

  const importBackup = useCallback(
    async (file: File) => {
      let parsed;
      try {
        parsed = parseBackup(JSON.parse(await file.text()));
      } catch {
        showToast('Fichier illisible');
        return;
      }
      if ('error' in parsed) {
        showToast(parsed.error);
        return;
      }
      const backup = parsed.backup;
      // Une restauration écrase tout : elle se confirme, elle ne se devine pas.
      setIncoming({
        summary: summarize(backup),
        apply: () => {
          applyBackup(backup);
          // Les contextes lisent le stockage au montage : plutôt que de
          // réconcilier des états React déjà montés, on repart proprement.
          window.location.reload();
        },
      });
    },
    [showToast],
  );

  const syncNow = useCallback(async () => {
    setSyncBusy(true);
    const key = ensureSyncKey();
    setSyncKey(key);
    const res = await pushState(key);
    showToast(res.ok ? `Sauvegarde envoyée (${Math.round(res.bytes / 1024)} ko)` : res.error);
    setSyncBusy(false);
  }, [showToast]);

  const restoreFromKey = useCallback(async () => {
    const key = keyDraft.trim() || syncKey;
    if (!key || !isValidKey(key)) {
      showToast('Clé absente ou mal formée');
      return;
    }
    setSyncBusy(true);
    const res = await pullState(key);
    setSyncBusy(false);

    if (res.status === 'error') {
      showToast(res.error);
      return;
    }
    if (res.status === 'empty') {
      showToast('Aucune sauvegarde pour cette clé');
      return;
    }
    setIncoming({
      summary: summarize(res.backup),
      apply: () => {
        writeSyncKey(key);
        applyBackup(res.backup);
        window.location.reload();
      },
    });
  }, [keyDraft, syncKey, showToast]);


  return (
    <div className="vz-screen vz-up">
      <h1 className="vz-screen__title">Réglages</h1>

      <SectionLabel
        action={
          <Link to="/bankroll" className="vz-link">
            Gérer en détail <IconChevronRight size={13} />
          </Link>
        }
      >
        Bankroll
      </SectionLabel>
      <div className="vz-card">
        <div className="vz-balance">
          <small>Solde actuel</small>
          <strong className="vz-num">{formatMoney(bankroll, settings.currency)}</strong>
        </div>
        <div className="vz-row vz-gap">
          <button
            type="button"
            className="vz-btn vz-btn--primary vz-f1"
            onClick={() => setSheet('deposit')}
          >
            <IconArrowDown size={16} /> Dépôt
          </button>
          <button type="button" className="vz-btn vz-f1" onClick={() => setSheet('withdraw')}>
            <IconArrowUp size={16} /> Retrait
          </button>
        </div>
        <div className="vz-field">
          <span>Afficher les mises chiffrées sur les value bets</span>
          <Switch
            checked={settings.bankrollOn}
            onChange={(v) => update({ bankrollOn: v })}
            label="Afficher les mises chiffrées"
          />
        </div>
        <div className="vz-field vz-field--col">
          <div className="vz-field__head">
            <span>Fraction de Kelly</span>
            <small className="vz-note">
              Plafond {Math.round(KELLY_CAP * 100)} % / pari
            </small>
          </div>
          <SegGroup label="Fraction de Kelly">
            {KELLY_FRACTIONS.map((f) => (
              <SegButton
                key={f}
                active={settings.kellyFraction === f}
                onClick={() => update({ kellyFraction: f })}
              >
                {KELLY_LABEL[f]}
              </SegButton>
            ))}
          </SegGroup>
          <p className="vz-note">{KELLY_HINT[settings.kellyFraction]}</p>
        </div>
        <div className="vz-field vz-field--col">
          <div className="vz-field__head">
            <span>Clôture automatique des paris</span>
            <Switch
              checked={settings.autoSettle}
              onChange={(v) => update({ autoSettle: v })}
              label="Clôture automatique des paris"
            />
          </div>
          <p className="vz-note">
            Dès que le score final est publié, les paris tranchables sans
            ambiguïté se règlent seuls. Le score exact et les intervalles après
            prolongation restent manuels, et toute clôture est annulable.
          </p>
        </div>
      </div>

      {transactions.length > 0 && (
        <>
          <SectionLabel>Mouvements récents</SectionLabel>
          <div className="vz-stack">
            {transactions.slice(0, 5).map((t) => (
              <div className="vz-tx" key={t.id}>
                <span className={`vz-tx__ic ${t.amount >= 0 ? 'is-up' : 'is-down'}`}>
                  {t.kind === 'deposit' ? (
                    <IconArrowDown size={15} />
                  ) : t.kind === 'withdraw' ? (
                    <IconArrowUp size={15} />
                  ) : t.kind === 'win' ? (
                    <IconCheck size={14} />
                  ) : (
                    <IconX size={13} />
                  )}
                </span>
                <div className="vz-f1">
                  <strong className="vz-ellipsis">{t.label}</strong>
                  <small>{formatShortDate(t.ts)}</small>
                </div>
                <strong className={`vz-num ${t.amount >= 0 ? 'is-up' : 'is-down'}`}>
                  {formatPnl(t.amount, settings.currency)}
                </strong>
              </div>
            ))}
          </div>
        </>
      )}

      <SectionLabel>Alertes</SectionLabel>
      <div className="vz-card vz-card--rows">
        <div className="vz-field">
          <span>Notifications push</span>
          <Switch
            checked={settings.alertsEnabled && permission === 'granted'}
            onChange={(v) => {
              if (v && permission !== 'granted') onOpenPermission();
              else update({ alertsEnabled: v });
            }}
            label="Notifications push"
          />
        </div>
        <div className="vz-field vz-field--col">
          <div className="vz-field__head">
            <span>Seuil d'edge déclencheur</span>
            <strong className="vz-num vz-field__out">{settings.alertThreshold} %</strong>
          </div>
          <input
            type="range"
            min={4}
            max={15}
            step={1}
            value={settings.alertThreshold}
            onChange={(e) => update({ alertThreshold: Number(e.target.value) })}
            aria-label="Seuil d'edge déclencheur"
          />
        </div>

        {push?.supported && (
          <div className="vz-field vz-field--col">
            <div className="vz-field__head">
              <span>Recevoir même l’app fermée</span>
              <Switch
                checked={push.subscribed}
                disabled={!push.ready || pushBusy}
                onChange={(v) => void togglePush(v)}
                label="Recevoir les alertes même l’app fermée"
              />
            </div>
            <p className="vz-note">
              {push.ready
                ? push.subscribed
                  ? `Une alerte par jour au maximum, sur le meilleur pari au-dessus de ${settings.alertThreshold} % d’edge. Rebasculez le curseur puis réactivez pour changer le seuil enregistré.`
                  : 'Les alertes ci-dessus ne partent que si l’app est ouverte. Activez ceci pour les recevoir téléphone verrouillé.'
                : 'Indisponible : le serveur n’a pas de clés de notification configurées.'}
            </p>
          </div>
        )}
        <div className="vz-field">
          <span>Plage silencieuse</span>
          <strong className="vz-num">
            {String(QUIET_START).padStart(2, '0')}:00 – {String(QUIET_END).padStart(2, '0')}:00
          </strong>
        </div>
        <div className="vz-row vz-gap">
          <button type="button" className="vz-btn vz-btn--sm vz-f1" onClick={onOpenAlerts}>
            Centre d'alertes
          </button>
          <button type="button" className="vz-btn vz-btn--sm vz-f1" onClick={onOpenNotif}>
            Aperçu notif
          </button>
          <button type="button" className="vz-btn vz-btn--sm vz-f1" onClick={onOpenPermission}>
            Prompt
          </button>
        </div>
      </div>

      <SectionLabel>Affichage</SectionLabel>
      <div className="vz-card vz-card--rows">
        <div className="vz-field vz-field--col">
          <span>Devise</span>
          <SegGroup label="Devise">
            {CURRENCY_CODES.map((c: CurrencyCode) => (
              <SegButton
                key={c}
                active={settings.currency === c}
                onClick={() => update({ currency: c })}
              >
                {CURRENCIES[c].symbol}
              </SegButton>
            ))}
          </SegGroup>
        </div>
        <div className="vz-field vz-field--col">
          <span>Sport par défaut</span>
          <SegGroup label="Sport par défaut">
            {(Object.keys(SPORTS) as Sport[]).map((s) => (
              <SegButton
                key={s}
                active={settings.defaultSport === s}
                onClick={() => update({ defaultSport: s })}
              >
                {SPORTS[s].label}
              </SegButton>
            ))}
          </SegGroup>
        </div>
        <div className="vz-field vz-field--col">
          <span>Probabilités affichées en</span>
          <SegGroup label="Format des probabilités">
            {(['pct', 'cote'] as ProbFormat[]).map((f) => (
              <SegButton
                key={f}
                active={settings.probFormat === f}
                onClick={() => update({ probFormat: f })}
              >
                {f === 'pct' ? 'Pourcentage' : 'Cote équiv.'}
              </SegButton>
            ))}
          </SegGroup>
        </div>
        <div className="vz-field vz-field--col">
          <span>Thème</span>
          <SegGroup label="Thème">
            {(['dark', 'light'] as ThemeMode[]).map((t) => (
              <SegButton key={t} active={settings.theme === t} onClick={() => update({ theme: t })}>
                {t === 'dark' ? 'Sombre' : 'Clair · Claude'}
              </SegButton>
            ))}
          </SegGroup>
        </div>
      </div>

      <SectionLabel>Sauvegarde</SectionLabel>
      <div className="vz-card vz-card--rows">
        <p className="vz-note">
          Bankroll, paris suivis et mouvements vivent sur cet appareil seulement.
          Un « effacer les données du site », et tout disparaît : gardez une
          sauvegarde. Le jeton GitHub de l’écran Admin n’y figure jamais.
        </p>
        <div className="vz-row vz-gap vz-wrap">
          <button type="button" className="vz-btn vz-btn--sm vz-f1" onClick={exportBackup}>
            <IconArrowDown size={14} /> Exporter
          </button>
          <label className="vz-btn vz-btn--sm vz-f1 vz-btn--file">
            <IconArrowUp size={14} /> Importer
            <input
              type="file"
              accept="application/json,.json"
              onChange={(e) => {
                const file = e.target.files?.[0];
                // On vide le champ : réimporter le même fichier doit marcher.
                e.target.value = '';
                if (file) void importBackup(file);
              }}
            />
          </label>
        </div>

        {incoming && (
          <div className="vz-stopalert">
            <IconWarning size={18} />
            <div className="vz-f1">
              <strong>Restaurer cette sauvegarde ?</strong>
              <small>
                {incoming.summary.bets} pari(s), {incoming.summary.transactions} mouvement(s),
                bankroll {formatMoney(incoming.summary.bankroll, settings.currency)}
                {incoming.summary.exportedAt
                  ? ` · du ${formatShortDate(incoming.summary.exportedAt)}`
                  : ''}
                . Vos données actuelles seront remplacées.
              </small>
              <div className="vz-row vz-gap vz-wrap">
                <button
                  type="button"
                  className="vz-btn vz-btn--sm vz-btn--danger"
                  onClick={incoming.apply}
                >
                  Remplacer
                </button>
                <button
                  type="button"
                  className="vz-btn vz-btn--sm"
                  onClick={() => setIncoming(null)}
                >
                  Annuler
                </button>
              </div>
            </div>
          </div>
        )}

        {SYNC_AVAILABLE && (
          <>
            <div className="vz-field vz-field--col">
              <div className="vz-field__head">
                <span>Clé de synchronisation</span>
                {syncKey && (
                  <button
                    type="button"
                    className="vz-link"
                    onClick={() => setKeyVisible((v) => !v)}
                  >
                    {keyVisible ? 'Masquer' : 'Afficher'}
                  </button>
                )}
              </div>
              <p className="vz-note">
                Qui a cette clé a la sauvegarde. Collez-la sur un autre appareil pour
                y retrouver votre bankroll — il n’y a pas de mot de passe à retenir,
                mais pas de récupération possible non plus : gardez aussi le fichier.
              </p>
              {syncKey && keyVisible && <p className="vz-src vz-break">{syncKey}</p>}
              <div className="vz-row vz-gap vz-wrap">
                <button
                  type="button"
                  className="vz-btn vz-btn--sm vz-f1"
                  disabled={syncBusy}
                  onClick={() => void syncNow()}
                >
                  {syncKey ? 'Sauvegarder en ligne' : 'Activer la synchronisation'}
                </button>
                {syncKey && (
                  <button
                    type="button"
                    className="vz-btn vz-btn--sm vz-f1"
                    disabled={syncBusy}
                    onClick={() => void navigator.clipboard
                      ?.writeText(syncKey)
                      .then(() => showToast('Clé copiée'))
                      .catch(() => showToast('Copie impossible'))}
                  >
                    Copier la clé
                  </button>
                )}
              </div>
            </div>

            <div className="vz-field vz-field--col">
              <div className="vz-field__head">
                <span>Récupérer depuis une clé</span>
              </div>
              <input
                type="text"
                className="vz-input"
                placeholder="Coller la clé d’un autre appareil"
                value={keyDraft}
                onChange={(e) => setKeyDraft(e.target.value)}
                autoComplete="off"
                spellCheck={false}
              />
              <button
                type="button"
                className="vz-btn vz-btn--sm vz-btn--block"
                disabled={syncBusy || !keyDraft.trim()}
                onClick={() => void restoreFromKey()}
              >
                Récupérer
              </button>
            </div>
          </>
        )}
      </div>

      <SectionLabel>À propos / données</SectionLabel>
      <div className="vz-card vz-card--rows">
        <div className="vz-field">
          <span>Prédictions</span>
          <strong>{generatedAt ? timeAgo(generatedAt) : 'jamais récupérées'}</strong>
        </div>
        <div className="vz-field">
          <span>Provenance</span>
          <strong>
            {origin === 'network'
              ? 'réseau'
              : origin === 'cache'
                ? 'cache local'
                : origin === 'mock'
                  ? 'échantillons de démo'
                  : '—'}
          </strong>
        </div>
        <p className="vz-src">{DATA_BASE}</p>
        <p className="vz-note">
          Les modèles sont réentraînés chaque lundi, les prédictions publiées chaque jour à
          7 h UTC. Vizer ne prend aucun pari : aucun compte bookmaker n'est connecté.
        </p>
        <div className="vz-row vz-gap vz-wrap">
          <button type="button" className="vz-btn vz-btn--sm vz-f1" onClick={onOpenInstall}>
            Installer l'app
          </button>
          <button
            type="button"
            className="vz-btn vz-btn--sm vz-f1"
            onClick={() => void loadDemo()}
          >
            <IconDownload size={14} /> Données de démo
          </button>
        </div>
        <button
          type="button"
          className="vz-btn vz-btn--sm vz-btn--block vz-btn--danger"
          onClick={() => {
            clearDataCache();
            setCacheCleared(true);
            void refresh();
          }}
        >
          Vider le cache
        </button>
        {cacheCleared && (
          <p className="vz-note" role="status">
            Cache vidé — données rechargées depuis la source.
          </p>
        )}
        <button
          type="button"
          className="vz-btn vz-btn--sm vz-btn--block"
          onClick={onReplayOnboarding}
        >
          Rejouer l'onboarding
        </button>
      </div>

      <AmountSheet
        open={sheet !== null}
        title={sheet === 'withdraw' ? 'Retirer des fonds' : 'Déposer des fonds'}
        confirmLabel={sheet === 'withdraw' ? 'Confirmer le retrait' : 'Confirmer le dépôt'}
        showQuickChips
        max={sheet === 'withdraw' ? bankroll : undefined}
        overdraftMessage="Montant supérieur au solde disponible."
        projected={(a) =>
          formatMoney(
            sheet === 'withdraw' ? Math.max(0, bankroll - a) : bankroll + a,
            settings.currency,
          )
        }
        onConfirm={(a) => {
          if (sheet === 'withdraw') withdraw(a);
          else deposit(a);
          setSheet(null);
        }}
        onClose={() => setSheet(null)}
      />
    </div>
  );
}
