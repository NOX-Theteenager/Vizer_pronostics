"""
period_aggregator.py — Agrégation des tirs en stats par période (réplique 02b).

Transforme les fichiers play-by-play `shots_*.csv` (volumineux, lus par chunks
pour économiser la RAM) en :
  - period_stats.csv : une ligne par (gameId, team, period) avec goals, xGoals,
    shots_on_goal, csa_shots_for. Sert à entraîner les Poisson P1 dédiés.
  - csa_stats.csv    : Score-Adjusted Corsi % par (gameId, team).

Le gameId est reconstruit au format 10 chiffres (season * 1_000_000 + game_id)
pour être compatible avec le dataset agrégé principal.

Usage :
    from src.data.period_aggregator import PeriodAggregator
    agg = PeriodAggregator(data_dir='data')
    period_stats = agg.build(save=True)
"""
from __future__ import annotations

import gc
import time
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from ..utils import TEAM_REMAP


# Colonnes nécessaires du fichier shots (économie mémoire massive)
SHOT_COLS = ['game_id', 'season', 'teamCode', 'period', 'goal', 'xGoal',
             'shotWasOnGoal', 'homeTeamGoals', 'awayTeamGoals', 'isHomeTeam']

CHUNK_SIZE = 200_000


def _normalize_team_col(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise la colonne 'team' selon TEAM_REMAP."""
    if 'team' in df.columns:
        df['team'] = df['team'].replace(TEAM_REMAP)
    return df


class PeriodAggregator:
    """
    Agrège les fichiers shots en period_stats + csa_stats.

    Args:
        data_dir : dossier contenant les shots_*.csv
        verbose  : log de progression
    """

    def __init__(self, data_dir: str = 'data', verbose: bool = True):
        self.data_dir = Path(data_dir)
        self.verbose = verbose

    def _log(self, msg: str):
        if self.verbose:
            print(msg)

    def _aggregate_file(self, csv_path: Path, label: str) -> pd.DataFrame:
        """Agrège un fichier shots → (gameId, team, period) par chunks."""
        self._log(f"\n📊 Agrégation {label}...")
        t0 = time.time()

        # Détecter le séparateur (Moneypuck utilise ',' ou ';')
        with open(csv_path, 'r') as f:
            header = f.readline()
        sep = ',' if header.count(',') > header.count(';') else ';'

        # Mapper les colonnes réelles (les noms ont varié au fil des saisons)
        actual_cols = pd.read_csv(csv_path, sep=sep, nrows=0).columns.tolist()
        col_map = {}
        for needed in SHOT_COLS:
            for actual in actual_cols:
                if (actual.lower() == needed.lower()
                        or actual.lower().replace('_', '') == needed.lower().replace('_', '')):
                    col_map[needed] = actual
                    break

        if 'game_id' not in col_map or 'period' not in col_map or 'season' not in col_map:
            missing = [c for c in ['game_id', 'season', 'period'] if c not in col_map]
            self._log(f"   ⚠️  Colonnes manquantes {missing} dans {csv_path.name} — ignoré.")
            return pd.DataFrame()

        cols_to_read = list(col_map.values())
        aggregated_chunks = []
        n_chunks = n_rows = 0

        for chunk in pd.read_csv(csv_path, sep=sep, usecols=cols_to_read, chunksize=CHUNK_SIZE):
            n_chunks += 1
            n_rows += len(chunk)
            chunk = chunk.rename(columns={v: k for k, v in col_map.items()})

            # Périodes 1-3 uniquement (P4/P5 = OT/SO, hors scope)
            chunk = chunk[chunk['period'].between(1, 3)]
            if chunk.empty:
                continue

            chunk = chunk.rename(columns={'teamCode': 'team'})
            chunk = _normalize_team_col(chunk)

            # gameId complet 10 chiffres = season * 1_000_000 + game_id
            chunk['gameId'] = (chunk['season'].astype('int64') * 1_000_000
                               + chunk['game_id'].astype('int64'))

            # Score-Adjusted Corsi : pondération selon le différentiel de score
            if 'homeTeamGoals' in chunk.columns and 'isHomeTeam' in chunk.columns:
                chunk['score_diff_for_shooter'] = np.where(
                    chunk['isHomeTeam'] == 1,
                    chunk['homeTeamGoals'] - chunk['awayTeamGoals'],
                    chunk['awayTeamGoals'] - chunk['homeTeamGoals'],
                )
                abs_diff = chunk['score_diff_for_shooter'].abs()
                chunk['csa_shot'] = np.select(
                    [abs_diff <= 1, abs_diff == 2, abs_diff >= 3],
                    [1.0, 0.50, 0.25], default=1.0,
                )
            else:
                chunk['csa_shot'] = 1.0

            sog_agg = (('shotWasOnGoal', 'sum') if 'shotWasOnGoal' in chunk.columns
                       else ('goal', 'count'))
            agg = chunk.groupby(['gameId', 'team', 'period']).agg(
                goals=('goal', 'sum'),
                xGoals=('xGoal', 'sum'),
                shots_on_goal=sog_agg,
                csa_shots_for=('csa_shot', 'sum'),
            ).reset_index()
            aggregated_chunks.append(agg)

            if self.verbose and n_chunks % 5 == 0:
                self._log(f"   Chunk {n_chunks:>3} ({n_rows/1e6:.1f}M lignes)")

        if not aggregated_chunks:
            return pd.DataFrame()

        full = pd.concat(aggregated_chunks, ignore_index=True)
        final = full.groupby(['gameId', 'team', 'period']).agg(
            goals=('goals', 'sum'),
            xGoals=('xGoals', 'sum'),
            shots_on_goal=('shots_on_goal', 'sum'),
            csa_shots_for=('csa_shots_for', 'sum'),
        ).reset_index()
        self._log(f"   ✓ {n_rows:,} tirs → {len(final):,} lignes en {time.time()-t0:.0f}s")
        del aggregated_chunks, full
        gc.collect()
        return final

    def build(self, save: bool = True,
              output_filename: str = 'period_stats.csv',
              csa_filename: str = 'csa_stats.csv') -> pd.DataFrame:
        """
        Agrège TOUS les fichiers shots_*.csv présents → period_stats + csa_stats.

        Detecte automatiquement tous les fichiers shots (historique + saisons),
        donc une nouvelle saison est intégrée sans modifier le code.
        """
        shot_files = sorted(self.data_dir.glob('shots_*.csv'))
        if not shot_files:
            self._log("ℹ️  Aucun fichier shots_*.csv — period_stats non généré "
                      "(les markets P1 utiliseront le fallback 30%).")
            return pd.DataFrame()

        self._log(f"🎯 Agrégation des tirs → period_stats")
        self._log(f"   {len(shot_files)} fichier(s) : {[f.name for f in shot_files]}")

        frames = []
        for f in shot_files:
            df = self._aggregate_file(f, f.name)
            if not df.empty:
                frames.append(df)
        if not frames:
            self._log("   ⚠️  Aucune donnée agrégée.")
            return pd.DataFrame()

        period_stats = pd.concat(frames, ignore_index=True)
        period_stats = period_stats.drop_duplicates(
            subset=['gameId', 'team', 'period'], keep='last')

        # CSA% par (gameId, team) = csa_for / (csa_for + csa_against)
        csa_per_game = (period_stats.groupby(['gameId', 'team'])['csa_shots_for']
                        .sum().reset_index())
        csa_per_game.columns = ['gameId', 'team', 'csa_for']
        game_totals = csa_per_game.groupby('gameId')['csa_for'].sum().reset_index()
        game_totals.columns = ['gameId', 'csa_total']
        csa_per_game = csa_per_game.merge(game_totals, on='gameId')
        csa_per_game['csa_against'] = csa_per_game['csa_total'] - csa_per_game['csa_for']
        csa_per_game['csa_pct'] = csa_per_game['csa_for'] / (csa_per_game['csa_total'] + 0.001)
        csa_per_game = csa_per_game[['gameId', 'team', 'csa_for', 'csa_against', 'csa_pct']]

        # Validation du ratio P1 (doit être ≈ 30%)
        if self.verbose:
            gbp = period_stats.groupby('period')['goals'].sum()
            total = gbp.sum()
            if total > 0 and 1 in gbp.index:
                ratio_p1 = gbp[1] / total
                ok = "✅" if 0.27 <= ratio_p1 <= 0.32 else "⚠️ écart"
                self._log(f"   Ratio P1 réel : {ratio_p1:.1%} {ok}")

        if save:
            out = self.data_dir / output_filename
            period_stats.to_csv(out, index=False)
            csa_out = self.data_dir / csa_filename
            csa_per_game.to_csv(csa_out, index=False)
            self._log(f"✅ {output_filename} : {len(period_stats):,} lignes "
                      f"({period_stats['gameId'].nunique():,} matchs)")
            self._log(f"✅ {csa_filename} : {len(csa_per_game):,} lignes "
                      f"(CSA% moyen {csa_per_game['csa_pct'].mean():.1%})")

        return period_stats
