import { useToast } from '../context/ToastContext';
import { IconX } from './Icons';

/** Toast global, ancré au-dessus de la barre de navigation. */
export function ToastHost() {
  const { toast, runUndo, dismissToast } = useToast();
  if (!toast) return null;

  return (
    <div className="vz-toast" role="status" aria-live="polite">
      <span className="vz-f1">{toast.msg}</span>
      {toast.undo && (
        <button type="button" className="vz-toast__undo" onClick={runUndo}>
          Annuler
        </button>
      )}
      <button
        type="button"
        className="vz-toast__close"
        onClick={dismissToast}
        aria-label="Fermer la notification"
      >
        <IconX size={11} />
      </button>
    </div>
  );
}
