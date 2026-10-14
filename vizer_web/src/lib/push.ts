/**
 * Abonnement aux notifications hors application.
 *
 * Jusqu'ici, une alerte ne partait que si l'app était ouverte : `useAlerts`
 * comparait les value bets au seuil et appelait l'API `Notification`. Un
 * téléphone verrouillé ne recevait rien, parce qu'un push ne part pas du
 * navigateur mais d'un serveur.
 *
 * Ce module ne fait que le va-et-vient avec `/api/push`. Il reste muet si le
 * déploiement n'est pas configuré — mieux vaut pas d'option qu'une option qui
 * ne produit rien.
 */

export interface PushStatus {
  /** Le navigateur sait faire du push. */
  supported: boolean;
  /** Le serveur a ses clés et son store. */
  ready: boolean;
  /** Ce navigateur est déjà abonné. */
  subscribed: boolean;
}

const VAPID_URL = '/api/push/vapid';
const SUBSCRIBE_URL = '/api/push/subscribe';

export function pushSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window
  );
}

/**
 * La clé VAPID voyage en base64url ; `applicationServerKey` veut des octets.
 */
function toBytes(base64url: string): Uint8Array {
  const padded = base64url.replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(padded + '='.repeat((4 - (padded.length % 4)) % 4));
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

async function serverKey(): Promise<string | null> {
  try {
    const res = await fetch(VAPID_URL, { cache: 'no-store' });
    if (!res.ok) return null;
    const body = (await res.json()) as { ready?: boolean; publicKey?: string | null };
    return body.ready && body.publicKey ? body.publicKey : null;
  } catch {
    return null;
  }
}

async function currentSubscription(): Promise<PushSubscription | null> {
  if (!pushSupported()) return null;
  try {
    const reg = await navigator.serviceWorker.ready;
    return await reg.pushManager.getSubscription();
  } catch {
    return null;
  }
}

export async function pushStatus(): Promise<PushStatus> {
  const supported = pushSupported();
  if (!supported) return { supported: false, ready: false, subscribed: false };
  const [key, sub] = await Promise.all([serverKey(), currentSubscription()]);
  return { supported: true, ready: key !== null, subscribed: sub !== null };
}

/**
 * Abonne ce navigateur. Demande la permission si elle n'a pas été donnée.
 *
 * Retourne un message d'échec plutôt que de lever : l'appelant affiche un
 * toast, il n'a rien de mieux à faire d'une exception.
 */
export async function subscribePush(threshold: number): Promise<string | null> {
  if (!pushSupported()) return 'Ce navigateur ne gère pas les notifications.';

  const key = await serverKey();
  if (!key) return 'Notifications non configurées sur le serveur.';

  if (Notification.permission !== 'granted') {
    const granted = await Notification.requestPermission();
    if (granted !== 'granted') return 'Permission refusée.';
  }

  try {
    const reg = await navigator.serviceWorker.ready;
    // Un abonnement existant peut porter une autre clé serveur (clés VAPID
    // régénérées) : on le remplace plutôt que de le réutiliser à l'aveugle.
    const existing = await reg.pushManager.getSubscription();
    if (existing) await existing.unsubscribe();

    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: toBytes(key) as BufferSource,
    });

    const res = await fetch(SUBSCRIBE_URL, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ action: 'subscribe', subscription: sub.toJSON(), threshold }),
    });
    if (!res.ok) {
      await sub.unsubscribe();
      return 'Le serveur a refusé l’abonnement.';
    }
    return null;
  } catch (e) {
    return e instanceof Error ? e.message : 'Abonnement impossible.';
  }
}

export async function unsubscribePush(): Promise<string | null> {
  const sub = await currentSubscription();
  if (!sub) return null;
  try {
    await fetch(SUBSCRIBE_URL, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ action: 'unsubscribe', subscription: sub.toJSON() }),
    });
  } catch {
    // Le retrait côté serveur a échoué : l'abonnement sera purgé au premier
    // envoi (404/410). On désabonne quand même le navigateur.
  }
  try {
    await sub.unsubscribe();
    return null;
  } catch (e) {
    return e instanceof Error ? e.message : 'Désabonnement impossible.';
  }
}
