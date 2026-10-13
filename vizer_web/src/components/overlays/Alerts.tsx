import { useNavigate } from 'react-router-dom';
import { useSettings } from '../../context/SettingsContext';
import { useAlerts, notificationBody, type PermissionState } from '../../hooks/useAlerts';
import { dayPhrase, formatEdge, formatOdds, formatTime } from '../../lib/format';
import { IconBell, IconBolt } from '../Icons';
import { LeagueTag } from '../Primitives';
import { FullOverlay, Sheet } from '../Sheet';
import { VizerMark } from '../Shell';

/** Centre d'alertes in-app. */
export function AlertsSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { alerts } = useAlerts();
  const navigate = useNavigate();

  return (
    <Sheet open={open} title="⚡ Alertes du jour" onClose={onClose}>
      {alerts.length === 0 ? (
        <div className="vz-empty vz-empty--accent">
          <span className="vz-empty__ic">
            <IconBell size={28} />
          </span>
          <h3>Aucune alerte</h3>
          <p>Aucun value bet ne dépasse ton seuil d'edge aujourd'hui.</p>
        </div>
      ) : (
        <div className="vz-stack">
          {alerts.map((vb) => (
            <button
              key={vb.id}
              type="button"
              className="vz-alert"
              onClick={() => {
                onClose();
                navigate(`/match/${vb.gameId}`);
              }}
            >
              <div className="vz-alert__top">
                <span>
                  <IconBolt size={12} /> {vb.marketLabel} · {vb.selectionLabel}
                </span>
                <strong className="vz-num">{formatEdge(vb.edge)}</strong>
              </div>
              <div className="vz-alert__meta">
                <LeagueTag sport={vb.sport} />
                {vb.away}–{vb.home} · @ {formatOdds(vb.bookmakerOdds)} ·{' '}
                {dayPhrase(vb.commenceTime)} {formatTime(vb.commenceTime)}
              </div>
            </button>
          ))}
        </div>
      )}
    </Sheet>
  );
}

/** Prompt de permission — jamais à froid, toujours sur action. */
export function PermissionPrompt({
  open,
  permission,
  onEnable,
  onClose,
}: {
  open: boolean;
  permission: PermissionState;
  onEnable: () => void;
  onClose: () => void;
}) {
  const blocked = permission === 'denied';
  const unsupported = permission === 'unsupported';

  return (
    <FullOverlay open={open} label="Activer les alertes" className="vz-perm">
      <div className="vz-perm__card">
        <span className="vz-perm__ic">
          <IconBolt size={34} />
        </span>
        <h3>
          {blocked
            ? 'Notifications bloquées'
            : unsupported
              ? 'Notifications indisponibles'
              : 'Sois prévenu des gros edges'}
        </h3>
        <p>
          {blocked
            ? 'Elles ont été refusées pour ce site. Réautorise-les dans les réglages du navigateur, puis reviens ici.'
            : unsupported
              ? "Ce navigateur ne gère pas les notifications. Le centre d'alertes in-app reste disponible."
              : 'Une notification dès que le modèle détecte un value bet au-dessus de ton seuil. Jamais de spam — que l’essentiel.'}
        </p>
        {!blocked && !unsupported && (
          <button type="button" className="vz-btn vz-btn--primary vz-btn--block" onClick={onEnable}>
            Activer les alertes
          </button>
        )}
        <button type="button" className="vz-btn vz-btn--plain vz-btn--block" onClick={onClose}>
          {blocked || unsupported ? 'Fermer' : 'Plus tard'}
        </button>
      </div>
    </FullOverlay>
  );
}

/** Aperçu de la notification système, tel qu'il apparaîtra sur l'écran verrouillé. */
export function NotifPreview({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { alerts } = useAlerts();
  const { settings } = useSettings();
  const top = alerts[0];

  const now = new Date();
  const time = formatTime(now.toISOString());
  const day = now.toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' });

  return (
    <FullOverlay open={open} label="Aperçu de notification" className="vz-notif" onBackdrop={onClose}>
      <div className="vz-notif__day">{day}</div>
      <div className="vz-notif__clock vz-num">{time}</div>
      <div className="vz-notif__card">
        <div className="vz-notif__head">
          <VizerMark size={22} />
          <span>VIZER</span>
          <span className="vz-f1" />
          <span className="vz-notif__when">maintenant</span>
        </div>
        <strong>
          <IconBolt size={15} />{' '}
          {top ? `Value bet ${formatEdge(top.edge)}` : 'Aucun value bet au-dessus du seuil'}
        </strong>
        <p>
          {top
            ? notificationBody(top)
            : `Rien ne dépasse ${settings.alertThreshold} % d'edge pour l'instant.`}
        </p>
      </div>
      <div className="vz-notif__hint">Touchez pour fermer</div>
    </FullOverlay>
  );
}

/** Invitation à installer la PWA. */
export function InstallPrompt({
  open,
  canInstall,
  onInstall,
  onClose,
}: {
  open: boolean;
  canInstall: boolean;
  onInstall: () => void;
  onClose: () => void;
}) {
  return (
    <Sheet open={open} title="Installer Vizer" onClose={onClose}>
      <div className="vz-install">
        <VizerMark size={82} />
        <p>
          Ajoute Vizer à ton écran d'accueil : accès plein écran, consultation hors-ligne,
          alertes push.
        </p>
        {canInstall ? (
          <button
            type="button"
            className="vz-btn vz-btn--primary vz-btn--block"
            onClick={onInstall}
          >
            Ajouter à l'écran d'accueil
          </button>
        ) : (
          <p className="vz-note">
            Ton navigateur ne propose pas d'installation automatique ici. Sur iOS :
            <strong> Partager → Sur l'écran d'accueil</strong>. Sur Android :
            <strong> menu ⋮ → Installer l'application</strong>.
          </p>
        )}
        <button type="button" className="vz-btn vz-btn--plain vz-btn--block" onClick={onClose}>
          Plus tard
        </button>
      </div>
    </Sheet>
  );
}
