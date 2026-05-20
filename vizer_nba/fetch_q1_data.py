#!/usr/bin/env python
"""
fetch_q1_data.py — Récupère les box scores par quart-temps pour les matchs NBA.

Pour chaque GAME_ID dans data/NBA_GAMES.csv (filtré sur les saisons utiles),
appelle nba_api BoxScoreSummaryV2 et extrait les colonnes PTS_QTR1, PTS_QTR2,
PTS_QTR3, PTS_QTR4 (+ OT) pour chaque équipe.

Sortie : data/NBA_Q1_SCORES.csv au format "2 lignes par match" (symétrique à
NBA_GAMES.csv) avec colonnes :
    GAME_ID, TEAM_ID, PTS_QTR1, PTS_QTR2, PTS_QTR3, PTS_QTR4, PTS_OT

Robustesse :
- Resume automatique : skip les GAME_IDs déjà fetchés
- Rate-limited : sleep configurable entre appels (défaut 0.6s)
- Retry exponential backoff sur 429 et erreurs réseau
- Checkpoint fréquent : flush sur disque toutes les N matchs
- Sigterm-safe : Ctrl-C → flush avant exit

Usage :
    python fetch_q1_data.py                              # toutes saisons depuis 22020
    python fetch_q1_data.py --start 22022 --end 22025    # range custom
    python fetch_q1_data.py --sleep 0.4                  # rate plus agressif
    python fetch_q1_data.py --max-games 100              # test rapide
"""
from __future__ import annotations

import argparse
import signal
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd
from tqdm import tqdm

# Supprimer les warnings nba_api (BoxScoreSummaryV2 deprecated etc.)
# Match par message car le filtre par module ne capture pas toujours.
warnings.filterwarnings('ignore', message=r'.*BoxScoreSummary.*')
warnings.filterwarnings('ignore', category=UserWarning)
warnings.filterwarnings('ignore', category=DeprecationWarning)

# Import nba_api (lazy : seulement si on entre dans main)


CHECKPOINT_EVERY = 25       # flush sur disque tous les N matchs
DEFAULT_SLEEP = 0.8         # secondes entre appels API
MAX_RETRIES = 1             # retries sur erreurs transitoires (1 = un seul retry, suffisant si les GAME_IDs sont corrects)
HTTP_TIMEOUT = 10           # timeout HTTP par appel
CACHE_FILE = "data/NBA_Q1_SCORES.csv"


# Variable globale pour permettre flush sur Ctrl-C
_pending_records: list[dict] = []
_output_path: Path = Path(CACHE_FILE)


def setup_sigterm_handler(records_ref: list, path: Path):
    """Flush en cas de Ctrl-C / SIGTERM."""
    def handler(signum, frame):
        print(f"\n⚠️  Signal {signum} reçu — flush en cours...", file=sys.stderr)
        flush_records(records_ref, path)
        print(f"✓ Sauvegardé. Vous pouvez relancer le script — il reprendra où il s'est arrêté.",
              file=sys.stderr)
        sys.exit(130)
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


def flush_records(records: list[dict], path: Path) -> int:
    """Append les records pending au CSV. Retourne le nombre flushed."""
    if not records:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    new_df = pd.DataFrame(records)
    # Normaliser : GAME_ID sur 10 chars
    new_df['GAME_ID'] = new_df['GAME_ID'].astype(str).str.zfill(10)
    if path.exists():
        existing = pd.read_csv(path, dtype={'GAME_ID': str})
        existing['GAME_ID'] = existing['GAME_ID'].astype(str).str.zfill(10)
        combined = pd.concat([existing, new_df], ignore_index=True)
        # Déduplique (au cas où, idempotence)
        combined = combined.drop_duplicates(subset=['GAME_ID', 'TEAM_ID'], keep='last')
    else:
        combined = new_df
    combined.to_csv(path, index=False)
    n = len(records)
    records.clear()
    return n


def load_existing(path: Path) -> tuple[set[str], int]:
    """
    Retourne (set des GAME_IDs valides déjà fetchés, nombre de records invalides purgés).

    Un record est considéré valide si PTS_QTR1 est renseigné. Les records avec
    PTS_QTR1 vide sont purgés du CSV pour être retentés.
    Les GAME_IDs sont normalisés à 10 caractères (zfill) pour matcher avec la
    source NBA_GAMES.csv qui peut avoir perdu les zéros de gauche.
    """
    if not path.exists():
        return set(), 0
    df = pd.read_csv(path, dtype={'GAME_ID': str})
    df['GAME_ID'] = df['GAME_ID'].str.zfill(10)

    # Identifier les GAME_IDs invalides (au moins une ligne avec PTS_QTR1 NaN)
    invalid_mask = df['PTS_QTR1'].isna()
    invalid_game_ids = set(df.loc[invalid_mask, 'GAME_ID'].unique())

    if invalid_game_ids:
        df_clean = df[~df['GAME_ID'].isin(invalid_game_ids)].copy()
        df_clean.to_csv(path, index=False)
        n_purged = len(df) - len(df_clean)
    else:
        df_clean = df
        n_purged = 0

    return set(df_clean['GAME_ID'].unique()), n_purged


def _extract_line_score_records(df) -> list[dict]:
    """
    Extrait les records d'une line_score, en gérant les schémas connus :
    - V2 (snake_case)        : PTS_QTR1..QTR4, PTS_OT1..OT10, TEAM_ID, GAME_ID
    - V3 (camelCase v1)      : pointsQtr1..Qtr4 (théorique)
    - V3 (camelCase v2)      : ptsQtr1..Qtr4 (théorique)
    - V3 (camelCase officiel): period1Score..period4Score, period5Score+ pour les OT
    Retourne une liste de dicts avec colonnes normalisées en SNAKE_CASE.
    """
    if df is None or len(df) == 0:
        return []

    cols = set(df.columns)

    def pick(*candidates):
        for c in candidates:
            if c in cols:
                return c
        return None

    col_game_id = pick('GAME_ID', 'gameId')
    col_team_id = pick('TEAM_ID', 'teamId')
    col_q1 = pick('PTS_QTR1', 'pointsQtr1', 'ptsQtr1', 'period1Score')
    col_q2 = pick('PTS_QTR2', 'pointsQtr2', 'ptsQtr2', 'period2Score')
    col_q3 = pick('PTS_QTR3', 'pointsQtr3', 'ptsQtr3', 'period3Score')
    col_q4 = pick('PTS_QTR4', 'pointsQtr4', 'ptsQtr4', 'period4Score')

    if not all([col_game_id, col_team_id, col_q1]):
        print(f"  ⚠️  Colonnes inattendues : {sorted(cols)[:20]}", file=sys.stderr)
        return []

    # Détecter colonnes OT (V2 : PTS_OT1..OT10 ; V3 : period5Score..period14Score)
    ot_cols = []
    for i in range(1, 11):
        c = pick(f'PTS_OT{i}', f'pointsOt{i}', f'ptsOt{i}', f'period{4 + i}Score')
        if c:
            ot_cols.append(c)

    records = []
    for _, row in df.iterrows():
        ot_total = 0
        for c in ot_cols:
            v = row.get(c)
            if pd.notna(v):
                try:
                    ot_total += int(v)
                except (ValueError, TypeError):
                    pass

        def safe_int(col):
            if col is None:
                return None
            v = row.get(col)
            if pd.isna(v):
                return None
            try:
                return int(v)
            except (ValueError, TypeError):
                return None

        records.append({
            'GAME_ID': str(row[col_game_id]),
            'TEAM_ID': int(row[col_team_id]),
            'PTS_QTR1': safe_int(col_q1),
            'PTS_QTR2': safe_int(col_q2),
            'PTS_QTR3': safe_int(col_q3),
            'PTS_QTR4': safe_int(col_q4),
            'PTS_OT': ot_total,
        })
    return records


def fetch_one_game(game_id: str, retries_left: int = MAX_RETRIES,
                    prefer_v3: bool = True) -> list[dict] | None:
    """
    Fetch les line scores pour un GAME_ID. Essaie V3 d'abord (recommandé),
    fallback V2 si V3 indisponible.

    Retourne 2 records (1 par équipe) ou None si erreur définitive.
    """
    from requests.exceptions import RequestException

    # Choisir l'endpoint
    endpoints_to_try = []
    if prefer_v3:
        from nba_api.stats.endpoints import boxscoresummaryv3
        endpoints_to_try.append(('V3', boxscoresummaryv3.BoxScoreSummaryV3))
    from nba_api.stats.endpoints import boxscoresummaryv2
    endpoints_to_try.append(('V2', boxscoresummaryv2.BoxScoreSummaryV2))

    last_error = None
    for label, EndpointClass in endpoints_to_try:
        try:
            bs = EndpointClass(game_id=game_id, timeout=HTTP_TIMEOUT)
            ls_df = bs.line_score.get_data_frame()
        except RequestException as e:
            last_error = e
            if retries_left > 0:
                wait = 2 ** (MAX_RETRIES - retries_left)
                time.sleep(wait)
                return fetch_one_game(game_id, retries_left - 1, prefer_v3=prefer_v3)
            continue
        except Exception as e:
            last_error = e
            msg = str(e).lower()
            if 'rate' in msg or 'timeout' in msg or 'connection' in msg:
                if retries_left > 0:
                    wait = 2 ** (MAX_RETRIES - retries_left)
                    time.sleep(wait)
                    return fetch_one_game(game_id, retries_left - 1, prefer_v3=prefer_v3)
            # Si JSONDecodeError ou autre, essaie l'endpoint suivant
            continue

        records = _extract_line_score_records(ls_df)
        # Records valides = au moins une équipe avec PTS_QTR1 renseigné.
        # Sinon, considérer comme échec et essayer l'endpoint suivant.
        if records and any(r.get('PTS_QTR1') is not None for r in records):
            return records
        # Sinon (records vides ou tous None), essaie l'endpoint suivant

    print(f"  ✗ {game_id} : tous endpoints ont échoué ({type(last_error).__name__ if last_error else 'no data'})",
          file=sys.stderr)
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Fetch des box scores par quart-temps via nba_api",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--games-csv', default='data/NBA_GAMES.csv',
                        help='CSV source (défaut: data/NBA_GAMES.csv)')
    parser.add_argument('--output', default=CACHE_FILE,
                        help=f'CSV de sortie (défaut: {CACHE_FILE})')
    parser.add_argument('--start', type=int, default=22020,
                        help='Saison de début (défaut: 22020)')
    parser.add_argument('--end', type=int, default=22025,
                        help='Saison de fin (défaut: 22025, inclusif)')
    parser.add_argument('--sleep', type=float, default=DEFAULT_SLEEP,
                        help=f'Secondes entre appels API (défaut: {DEFAULT_SLEEP})')
    parser.add_argument('--max-games', type=int, default=None,
                        help='Limite (test rapide). None = tous les matchs.')
    parser.add_argument('--checkpoint-every', type=int, default=CHECKPOINT_EVERY,
                        help=f'Flush tous les N matchs (défaut: {CHECKPOINT_EVERY})')
    args = parser.parse_args()

    output_path = Path(args.output)

    print("=" * 70)
    print("🏀 FETCH BOX SCORES Q1 NBA")
    print("=" * 70)
    print(f"Source        : {args.games_csv}")
    print(f"Output        : {args.output}")
    print(f"Saisons       : {args.start} → {args.end}")
    print(f"Rate limit    : {args.sleep}s entre appels")
    print(f"Checkpoint    : tous les {args.checkpoint_every} matchs")
    print()

    # Charger les GAME_IDs à fetcher
    print("📂 Chargement de la liste des matchs...", file=sys.stderr)
    games_df = pd.read_csv(args.games_csv, dtype={'GAME_ID': str})
    games_df = games_df[
        (games_df['SEASON_ID'] >= args.start) &
        (games_df['SEASON_ID'] <= args.end)
    ]
    # CRITIQUE : zfill(10) — NBA Stats exige des GAME_IDs sur 10 caractères.
    # Si le CSV stocke "22500001" sans préfixe "002", l'API retourne KeyError.
    games_df['GAME_ID'] = games_df['GAME_ID'].astype(str).str.zfill(10)
    target_game_ids = sorted(games_df['GAME_ID'].unique())
    print(f"  ✓ {len(target_game_ids):,} matchs uniques à considérer", file=sys.stderr)
    # Sanity check : afficher quelques exemples pour repérer un mauvais format
    print(f"  ℹ Exemples GAME_IDs : {target_game_ids[:3]}", file=sys.stderr)

    # Filtrer ceux déjà fetchés
    already, n_purged = load_existing(output_path)
    if n_purged > 0:
        print(f"  🧹 {n_purged} record(s) invalide(s) purgé(s) du cache (seront retentés)",
              file=sys.stderr)
    print(f"  ✓ {len(already):,} matchs valides en cache (seront skipped)", file=sys.stderr)
    todo = [gid for gid in target_game_ids if gid not in already]
    print(f"  → {len(todo):,} matchs à fetcher", file=sys.stderr)

    if args.max_games:
        todo = todo[:args.max_games]
        print(f"  ⚠ Limité à {len(todo)} matchs (--max-games)", file=sys.stderr)

    if not todo:
        print("\n✅ Rien à faire — toutes les données Q1 sont déjà cachées.")
        return 0

    # Estimation
    est_min = (len(todo) * args.sleep) / 60
    print(f"\n⏱️  Estimation : ~{est_min:.0f}min ({len(todo)} × {args.sleep}s)", file=sys.stderr)
    print()

    # Setup signal handler (flush sur Ctrl-C)
    records_buffer: list[dict] = []
    setup_sigterm_handler(records_buffer, output_path)

    # Fetch loop
    successes = 0
    failures = 0
    t0 = time.time()
    last_flush = time.time()

    try:
        for game_id in tqdm(todo, desc='Fetching Q1', unit='game'):
            records = fetch_one_game(game_id)
            if records:
                records_buffer.extend(records)
                successes += 1
            else:
                failures += 1

            # Flush périodique
            if len(records_buffer) >= args.checkpoint_every * 2:  # *2 car 2 records par match
                n = flush_records(records_buffer, output_path)
                tqdm.write(f"  💾 Checkpoint : +{n} records → {output_path}")
                last_flush = time.time()

            time.sleep(args.sleep)
    finally:
        # Flush final même en cas d'exception
        if records_buffer:
            n = flush_records(records_buffer, output_path)
            print(f"\n💾 Flush final : +{n} records → {output_path}", file=sys.stderr)

    duration = time.time() - t0
    print()
    print("=" * 70)
    print("✅ TERMINÉ")
    print("=" * 70)
    print(f"Durée       : {duration / 60:.1f}min")
    print(f"Succès      : {successes:,} / {len(todo):,}")
    print(f"Échecs      : {failures:,}")
    if failures > 0:
        print(f"  → Relancer le script pour retenter les échecs (les succès sont déjà cachés)")
    print(f"Fichier     : {output_path}")
    if output_path.exists():
        df = pd.read_csv(output_path, dtype={'GAME_ID': str})
        print(f"Total cache : {len(df):,} records ({df['GAME_ID'].nunique():,} matchs distincts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
