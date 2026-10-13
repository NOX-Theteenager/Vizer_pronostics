import { useCallback, useState } from 'react';
import { useSettings } from '../../context/SettingsContext';
import { useToast } from '../../context/ToastContext';
import { formatMoney, formatPnl } from '../../lib/currency';
import { Switch } from '../Primitives';
import { Sheet } from '../Sheet';
import { VizerMark } from '../Shell';
import type { FollowedBet } from '../../types/bankroll';

/**
 * Partage d'un pari : aperçu carré à l'écran, puis export PNG 1080×1080 par
 * canvas. Aucun service externe — l'image est fabriquée dans le navigateur.
 */
export function ShareSheet({ bet, onClose }: { bet: FollowedBet | null; onClose: () => void }) {
  const { settings } = useSettings();
  const { showToast } = useToast();
  const [withStake, setWithStake] = useState(true);

  const won = bet?.status === 'won';
  const lost = bet?.status === 'lost';
  const color = won ? '#2ce08c' : lost ? '#ff5d5d' : '#f0885e';

  const resultLabel = useCallback((): string => {
    if (!bet) return '';
    if (won) {
      return `GAGNÉ${withStake && bet.pnl !== null ? ` · ${formatPnl(bet.pnl, settings.currency)}` : ''}`;
    }
    if (lost) return 'PERDU';
    const potential = Math.round(bet.stake * bet.odds);
    return `EN COURS${withStake ? ` · gain potentiel ${formatMoney(potential, settings.currency)}` : ''}`;
  }, [bet, won, lost, withStake, settings.currency]);

  /** Rend la carte en PNG 1080×1080. */
  const toBlob = useCallback(async (): Promise<Blob | null> => {
    if (!bet) return null;
    const W = 1080;
    const c = document.createElement('canvas');
    c.width = W;
    c.height = W;
    const x = c.getContext('2d');
    if (!x) return null;
    const F = getComputedStyle(document.body).fontFamily || 'system-ui';

    x.fillStyle = '#0b0d12';
    x.fillRect(0, 0, W, W);
    const g = x.createRadialGradient(W * 0.85, 0, 0, W * 0.85, 0, W * 0.7);
    g.addColorStop(0, 'rgba(240,136,94,.32)');
    g.addColorStop(1, 'rgba(240,136,94,0)');
    x.fillStyle = g;
    x.fillRect(0, 0, W, W);

    // Marque : les deux lames du « V », dessinées plutôt que chargées.
    const mark = (ox: number, oy: number, s: number) => {
      const p = (fx: number, fy: number): [number, number] => [ox + fx * s, oy + fy * s];
      x.fillStyle = '#2ce08c';
      x.beginPath();
      x.moveTo(...p(0.09, 0.19));
      x.lineTo(...p(0.31, 0.19));
      x.lineTo(...p(0.52, 0.78));
      x.lineTo(...p(0.42, 0.88));
      x.closePath();
      x.fill();
      x.fillStyle = '#c9d2dd';
      x.beginPath();
      x.moveTo(...p(0.91, 0.19));
      x.lineTo(...p(0.69, 0.19));
      x.lineTo(...p(0.48, 0.78));
      x.lineTo(...p(0.58, 0.88));
      x.closePath();
      x.fill();
    };
    mark(64, 56, 104);

    x.fillStyle = '#f3f5f9';
    x.font = `900 46px ${F}`;
    x.fillText('VIZER', 186, 130);

    // Pastille de ligue, alignée à droite.
    x.font = `900 30px ${F}`;
    const lw = x.measureText(bet.league).width + 48;
    x.strokeStyle = 'rgba(240,136,94,.6)';
    x.lineWidth = 3;
    x.beginPath();
    x.roundRect(W - 70 - lw, 78, lw, 64, 32);
    x.stroke();
    x.fillStyle = '#f0885e';
    x.fillText(bet.league, W - 70 - lw + 24, 121);

    x.fillStyle = '#8b93a4';
    x.font = `800 36px ${F}`;
    x.fillText(bet.matchLabel, 70, 560);
    x.font = `900 36px ${F}`;
    x.fillText(bet.marketLabel, 70, 630);

    x.fillStyle = '#f3f5f9';
    x.font = `900 72px ${F}`;
    x.fillText(bet.selection, 70, 716, W - 140);

    x.fillStyle = '#8b93a4';
    x.font = `800 28px ${F}`;
    x.fillText('COTE', 70, 800);
    if (withStake) x.fillText('MISE', 380, 800);
    x.fillStyle = '#f3f5f9';
    x.font = `900 60px ${F}`;
    x.fillText(bet.odds.toFixed(2), 70, 862);
    if (withStake) x.fillText(formatMoney(bet.stake, settings.currency), 380, 862, W - 450);

    x.font = `900 40px ${F}`;
    const label = resultLabel();
    const rw = x.measureText(label).width + 60;
    x.fillStyle = `${color}22`;
    x.strokeStyle = `${color}88`;
    x.beginPath();
    x.roundRect(70, 912, rw, 84, 22);
    x.fill();
    x.stroke();
    x.fillStyle = color;
    x.fillText(label, 100, 968);

    return new Promise((res) => c.toBlob((b) => res(b), 'image/png'));
  }, [bet, withStake, settings.currency, color, resultLabel]);

  const download = useCallback(async () => {
    const blob = await toBlob();
    if (!blob) {
      showToast('Export indisponible');
      return;
    }
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'vizer-pari.png';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    showToast('Image téléchargée');
  }, [toBlob, showToast]);

  const share = useCallback(async () => {
    if (!bet) return;
    const text = `${bet.marketLabel} · ${bet.selection} @ ${bet.odds.toFixed(2)} — ${bet.matchLabel} (${resultLabel()}) via Vizer`;
    try {
      const blob = await toBlob();
      if (blob) {
        const file = new File([blob], 'vizer-pari.png', { type: 'image/png' });
        if (navigator.canShare?.({ files: [file] })) {
          await navigator.share({ files: [file], text });
          return;
        }
      }
      if (navigator.share) {
        await navigator.share({ text });
        return;
      }
    } catch (e) {
      // L'utilisateur a fermé la feuille de partage : ce n'est pas une erreur.
      if (e instanceof Error && e.name === 'AbortError') return;
    }
    try {
      await navigator.clipboard.writeText(text);
      showToast('Texte du pari copié');
    } catch {
      showToast('Partage indisponible sur cet appareil');
    }
  }, [bet, toBlob, resultLabel, showToast]);

  if (!bet) return null;

  return (
    <Sheet open title="Partager le pari" onClose={onClose}>
      <div className="vz-share">
        <div className="vz-share__head">
          <VizerMark size={30} />
          <span className="vz-share__word">VIZER</span>
          <span className="vz-f1" />
          <span className="vz-share__league">{bet.league}</span>
        </div>
        <span className="vz-f1" />
        <div className="vz-share__match">{bet.matchLabel}</div>
        <div className="vz-share__market">{bet.marketLabel}</div>
        <div className="vz-share__sel">{bet.selection}</div>
        <div className="vz-share__nums">
          <div>
            <small>COTE</small>
            <strong className="vz-num">{bet.odds.toFixed(2)}</strong>
          </div>
          {withStake && (
            <div>
              <small>MISE</small>
              <strong className="vz-num">{formatMoney(bet.stake, settings.currency)}</strong>
            </div>
          )}
        </div>
        <div className="vz-share__result" style={{ ['--rc' as string]: color }}>
          {resultLabel()}
        </div>
      </div>

      <div className="vz-field">
        <span>Afficher la mise</span>
        <Switch checked={withStake} onChange={setWithStake} label="Afficher la mise" />
      </div>

      <div className="vz-row vz-gap">
        <button type="button" className="vz-btn vz-f1" onClick={() => void download()}>
          Télécharger l'image
        </button>
        <button type="button" className="vz-btn vz-btn--primary vz-f1" onClick={() => void share()}>
          Partager
        </button>
      </div>
    </Sheet>
  );
}
