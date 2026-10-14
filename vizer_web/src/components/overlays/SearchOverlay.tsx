import { useCallback, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useData } from '../../context/DataContext';
import { dayPhrase, formatTime } from '../../lib/format';
import { KEYS, readJson, writeJson } from '../../lib/storage';
import { SPORTS, type Game } from '../../types/model';
import { IconChevronLeft, IconChevronRight, IconClock, IconMic, IconSearch, IconX } from '../Icons';
import { TeamLogo } from '../TeamLogo';

/** Minimum nécessaire de l'API Web Speech (non typée par TS). */
interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  start: () => void;
  onresult: ((e: { results: { 0: { 0: { transcript: string } } } }) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
}
type SpeechCtor = new () => SpeechRecognitionLike;

const SUGGESTIONS = ['Canadiens', 'Lakers', 'Bruins', 'BTTS'];

/** Texte indexé d'un match : codes, noms, ligue, marchés de ses value bets. */
function searchBlob(g: Game): string {
  return [
    g.home,
    g.away,
    g.homeName,
    g.awayName,
    SPORTS[g.sport].league,
    SPORTS[g.sport].label,
    ...g.valueBets.map((v) => `${v.marketLabel} ${v.selectionLabel}`),
  ]
    .join(' ')
    .toLowerCase();
}

export function SearchOverlay({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { games } = useData();
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [voice, setVoice] = useState<'off' | 'on' | 'unsupported'>('off');
  const [recent, setRecent] = useState<string[]>(() =>
    readJson<string[]>(KEYS.recentSearches, []),
  );
  const inputRef = useRef<HTMLInputElement>(null);

  const q = query.trim().toLowerCase();
  const results = useMemo(
    () => (q ? games.filter((g) => searchBlob(g).includes(q)) : []),
    [games, q],
  );

  const remember = useCallback((term: string) => {
    const t = term.trim();
    if (!t) return;
    setRecent((prev) => {
      const next = [t, ...prev.filter((x) => x.toLowerCase() !== t.toLowerCase())].slice(0, 5);
      writeJson(KEYS.recentSearches, next);
      return next;
    });
  }, []);

  const startVoice = useCallback(() => {
    const w = window as unknown as { SpeechRecognition?: SpeechCtor; webkitSpeechRecognition?: SpeechCtor };
    const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
    if (!Ctor) {
      setVoice('unsupported');
      window.setTimeout(() => setVoice('off'), 2200);
      return;
    }
    try {
      const r = new Ctor();
      r.lang = 'fr-FR';
      r.interimResults = false;
      r.maxAlternatives = 1;
      setVoice('on');
      r.onresult = (e) => {
        const t = e.results[0][0].transcript;
        setQuery(t);
        remember(t);
        setVoice('off');
      };
      r.onerror = () => setVoice('off');
      r.onend = () => setVoice('off');
      r.start();
    } catch {
      setVoice('off');
    }
  }, [remember]);

  if (!open) return null;

  const openGame = (g: Game) => {
    remember(query);
    onClose();
    navigate(`/match/${g.id}`);
  };

  return (
    <div className="vz-search" role="dialog" aria-modal="true" aria-label="Rechercher un match">
      <div className="vz-search__bar">
        <button type="button" className="vz-iconbtn" onClick={onClose} aria-label="Retour">
          <IconChevronLeft size={18} />
        </button>
        <div className="vz-search__field">
          <IconSearch size={16} />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Rechercher un match, une équipe…"
            aria-label="Rechercher"
            autoFocus
          />
          {q && (
            <button type="button" onClick={() => setQuery('')} aria-label="Effacer">
              <IconX size={10} />
            </button>
          )}
        </div>
        <button
          type="button"
          className={`vz-iconbtn${voice === 'on' ? ' is-live' : ''}`}
          onClick={startVoice}
          aria-label="Recherche vocale"
        >
          <IconMic size={17} />
        </button>
      </div>

      <div className="vz-search__body vz-sc">
        {voice === 'on' && (
          <div className="vz-search__voice">
            <i /> À l'écoute… parle maintenant
          </div>
        )}
        {voice === 'unsupported' && (
          <p className="vz-note">
            <IconMic size={15} /> La saisie vocale n'est pas disponible sur cet appareil.
          </p>
        )}

        {q ? (
          results.length ? (
            <>
              <h4 className="vz-seclabel">
                {results.length} résultat{results.length > 1 ? 's' : ''} · tous sports
              </h4>
              <div className="vz-stack">
                {results.map((g) => (
                  <button key={g.id} type="button" className="vz-sres" onClick={() => openGame(g)}>
                    <span className="vz-sres__logos">
                      <TeamLogo sport={g.sport} code={g.home} size={24} />
                      <TeamLogo sport={g.sport} code={g.away} size={24} />
                    </span>
                    <span className="vz-f1">
                      <strong className="vz-ellipsis">
                        {g.homeName} — {g.awayName}
                      </strong>
                      <small className="vz-num">
                        {formatTime(g.commenceTime)} · {dayPhrase(g.commenceTime)}
                      </small>
                    </span>
                    <IconChevronRight size={14} />
                  </button>
                ))}
              </div>
            </>
          ) : (
            <div className="vz-empty vz-empty--accent">
              <span className="vz-empty__ic">
                <IconSearch size={30} />
              </span>
              <h3>Aucun match trouvé</h3>
              <p>Essaie un autre nom d'équipe (Lakers, Bruins, Canadiens…).</p>
            </div>
          )
        ) : (
          <>
            {recent.length > 0 && (
              <>
                <h4 className="vz-seclabel">
                  Recherches récentes
                  <button
                    type="button"
                    className="vz-link"
                    onClick={() => {
                      setRecent([]);
                      writeJson(KEYS.recentSearches, []);
                    }}
                  >
                    Effacer
                  </button>
                </h4>
                <div className="vz-stack">
                  {recent.map((t) => (
                    <button key={t} type="button" className="vz-sres" onClick={() => setQuery(t)}>
                      <IconClock size={15} />
                      <span className="vz-f1">{t}</span>
                    </button>
                  ))}
                </div>
              </>
            )}

            <div className="vz-search__idle">
              <h3>Rechercher un match</h3>
              <p>
                Par équipe, ligue (NHL, NBA) ou marché (BTTS, total…) — hockey et basket
                confondus.
              </p>
              <div className="vz-chiprow vz-chiprow--center">
                {SUGGESTIONS.map((s) => (
                  <button key={s} type="button" className="vz-chip" onClick={() => setQuery(s)}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
