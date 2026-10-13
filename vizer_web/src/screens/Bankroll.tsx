import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  IconArrowDown,
  IconArrowUp,
  IconCheck,
  IconDownload,
  IconEdit,
  IconWarning,
  IconX,
} from '../components/Icons';
import { Chip, MiniBar, SectionLabel } from '../components/Primitives';
import { AmountSheet } from '../components/overlays/AmountSheet';
import { useBankroll } from '../context/BankrollContext';
import { useSettings } from '../context/SettingsContext';
import { formatMoney, formatPnl } from '../lib/currency';
import { formatShortDate } from '../lib/format';
import type { Transaction, TxKind } from '../types/bankroll';

type TxFilter = 'all' | 'deposit' | 'withdraw' | 'bet';
type Sheet =
  | { kind: 'deposit' | 'withdraw' }
  | { kind: 'goal' | 'stop' }
  | { kind: 'edit'; tx: Transaction }
  | null;

/** Écran Bankroll : solde, objectif, stop-loss et tous les mouvements. */
export function Bankroll() {
  const navigate = useNavigate();
  const { settings } = useSettings();
  const {
    bankroll,
    goal,
    stopLoss,
    transactions,
    deposit,
    withdraw,
    setGoal,
    setStopLoss,
    editTransaction,
    deleteTransaction,
    exportTransactionsCsv,
  } = useBankroll();

  const [sheet, setSheet] = useState<Sheet>(null);
  const [filter, setFilter] = useState<TxFilter>('all');

  const list = useMemo(
    () =>
      transactions.filter((t) =>
        filter === 'all'
          ? true
          : filter === 'bet'
            ? t.kind === 'win' || t.kind === 'loss'
            : t.kind === filter,
      ),
    [transactions, filter],
  );

  const goalPct = goal > 0 ? Math.min(1, bankroll / goal) : 0;
  const belowStop = stopLoss > 0 && bankroll <= stopLoss;

  return (
    <div className="vz-screen vz-up">
      <div className="vz-screen__head">
        <button type="button" className="vz-back" onClick={() => navigate(-1)} aria-label="Retour">
          ‹
        </button>
        <h1>Bankroll</h1>
      </div>

      {belowStop && (
        <div className="vz-stopalert">
          <IconWarning size={18} />
          <div>
            <strong>Stop-loss atteint</strong>
            <small>Ta bankroll est sous ton seuil. Fais une pause avant de miser à nouveau.</small>
          </div>
        </div>
      )}

      <div className="vz-card">
        <div className="vz-balance vz-balance--xl">
          <small>Solde actuel</small>
          <strong className="vz-num">{formatMoney(bankroll, settings.currency)}</strong>
        </div>
        <div className="vz-row vz-gap">
          <button
            type="button"
            className="vz-btn vz-btn--primary vz-f1"
            onClick={() => setSheet({ kind: 'deposit' })}
          >
            <IconArrowDown size={15} /> Dépôt
          </button>
          <button
            type="button"
            className="vz-btn vz-f1"
            onClick={() => setSheet({ kind: 'withdraw' })}
          >
            <IconArrowUp size={15} /> Retrait
          </button>
        </div>
      </div>

      <div className="vz-card vz-card--rows">
        <div className="vz-field">
          <span className="vz-seclabel vz-seclabel--inline">Objectif</span>
          <button type="button" className="vz-link" onClick={() => setSheet({ kind: 'goal' })}>
            Modifier
          </button>
        </div>
        {goal > 0 ? (
          <>
            <div className="vz-field">
              <span>
                {formatMoney(bankroll, settings.currency)} / {formatMoney(goal, settings.currency)}
              </span>
              <strong className="vz-num vz-goal__pct">{Math.round(goalPct * 100)} %</strong>
            </div>
            <MiniBar
              ratio={goalPct}
              height={9}
              color={bankroll >= goal ? 'var(--value)' : 'var(--accent)'}
            />
          </>
        ) : (
          <p className="vz-note">
            Aucun objectif défini. Un objectif affiche une barre de progression ici.
          </p>
        )}
        <div className="vz-field">
          <div>
            <strong>Seuil stop-loss</strong>
            <small className="vz-note">
              {stopLoss > 0 ? formatMoney(stopLoss, settings.currency) : 'non défini'}
            </small>
          </div>
          <button type="button" className="vz-link" onClick={() => setSheet({ kind: 'stop' })}>
            Modifier
          </button>
        </div>
      </div>

      <SectionLabel
        action={
          <button type="button" className="vz-link" onClick={exportTransactionsCsv}>
            <IconDownload size={14} /> Export CSV
          </button>
        }
      >
        Historique
      </SectionLabel>

      <div className="vz-chiprow vz-sc">
        {(['all', 'deposit', 'withdraw', 'bet'] as TxFilter[]).map((f) => (
          <Chip key={f} active={filter === f} onClick={() => setFilter(f)}>
            {f === 'all' ? 'Tout' : f === 'deposit' ? 'Dépôts' : f === 'withdraw' ? 'Retraits' : 'Paris'}
          </Chip>
        ))}
      </div>

      {list.length === 0 ? (
        <p className="vz-note vz-note--center">Aucun mouvement pour ce filtre.</p>
      ) : (
        <div className="vz-stack">
          {list.map((t) => (
            <button
              key={t.id}
              type="button"
              className="vz-tx vz-tx--btn"
              onClick={() => setSheet({ kind: 'edit', tx: t })}
            >
              <span className={`vz-tx__ic ${t.amount >= 0 ? 'is-up' : 'is-down'}`}>
                <TxIcon kind={t.kind} />
              </span>
              <span className="vz-f1">
                <strong className="vz-ellipsis">{t.label}</strong>
                <small>{formatShortDate(t.ts)}</small>
              </span>
              <strong className={`vz-num ${t.amount >= 0 ? 'is-up' : 'is-down'}`}>
                {formatPnl(t.amount, settings.currency)}
              </strong>
              <IconEdit size={15} />
            </button>
          ))}
        </div>
      )}

      <AmountSheet
        open={sheet?.kind === 'deposit' || sheet?.kind === 'withdraw'}
        title={sheet?.kind === 'withdraw' ? 'Retirer des fonds' : 'Déposer des fonds'}
        confirmLabel={sheet?.kind === 'withdraw' ? 'Confirmer le retrait' : 'Confirmer le dépôt'}
        showQuickChips
        max={sheet?.kind === 'withdraw' ? bankroll : undefined}
        overdraftMessage="Montant supérieur au solde disponible."
        projected={(a) =>
          formatMoney(
            sheet?.kind === 'withdraw' ? Math.max(0, bankroll - a) : bankroll + a,
            settings.currency,
          )
        }
        onConfirm={(a) => {
          if (sheet?.kind === 'withdraw') withdraw(a);
          else deposit(a);
          setSheet(null);
        }}
        onClose={() => setSheet(null)}
      />

      <AmountSheet
        open={sheet?.kind === 'goal' || sheet?.kind === 'stop'}
        title={sheet?.kind === 'stop' ? 'Seuil stop-loss' : 'Objectif de bankroll'}
        hint={
          sheet?.kind === 'stop'
            ? "Si la bankroll passe sous ce seuil, Vizer t'alerte pour temporiser."
            : 'Le solde visé. Une barre de progression suit ton avancée.'
        }
        initial={sheet?.kind === 'stop' ? stopLoss : goal}
        confirmLabel="Enregistrer"
        onConfirm={(a) => {
          if (sheet?.kind === 'stop') setStopLoss(a);
          else setGoal(a);
          setSheet(null);
        }}
        onClose={() => setSheet(null)}
      />

      <AmountSheet
        open={sheet?.kind === 'edit'}
        title="Modifier le mouvement"
        hint={sheet?.kind === 'edit' ? sheet.tx.label : undefined}
        initial={sheet?.kind === 'edit' ? Math.abs(sheet.tx.amount) : 0}
        confirmLabel="Enregistrer"
        destructive={
          sheet?.kind === 'edit'
            ? {
                label: 'Supprimer',
                onClick: () => {
                  deleteTransaction(sheet.tx.id);
                  setSheet(null);
                },
              }
            : undefined
        }
        onConfirm={(a) => {
          if (sheet?.kind === 'edit') editTransaction(sheet.tx.id, a);
          setSheet(null);
        }}
        onClose={() => setSheet(null)}
      />
    </div>
  );
}

function TxIcon({ kind }: { kind: TxKind }) {
  if (kind === 'deposit') return <IconArrowDown size={15} />;
  if (kind === 'withdraw') return <IconArrowUp size={15} />;
  if (kind === 'win') return <IconCheck size={14} />;
  return <IconX size={13} />;
}
