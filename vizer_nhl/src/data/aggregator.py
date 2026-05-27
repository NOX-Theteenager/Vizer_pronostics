"""
aggregator.py — Reconstruction du dataset agrégé NHL depuis les CSVs Moneypuck.

Réplique fidèlement la logique du notebook 02_Agregation.ipynb :
  Étape 1 — Gardiens (GSAE)
  Étape 2 — Skaters & Lignes (star_impact, top_line_xGF, panic_score)
  Étape 3 — Données équipe + rolling stats multi-fenêtres (5/10/20/50)
  Étape 4 — Table finale Home vs Away + différentiels + cibles
  Bonus  — Fusion period_stats (goals_p1) si disponible

Produit dataset_agrege_vizer_nhl.csv, identique à la sortie du notebook.

Usage :
    from src.data.aggregator import NHLAggregator
    agg = NHLAggregator(data_dir='data')
    df_final = agg.build(save=True)
"""
from __future__ import annotations

import gc
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from ..utils import TEAM_REMAP


def normalize_teams(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise les codes équipe selon TEAM_REMAP (T.B→TBL, etc.)."""
    for col in ['team', 'playerTeam', 'homeTeam', 'awayTeam', 'opposingTeam']:
        if col in df.columns:
            df[col] = df[col].replace(TEAM_REMAP)
    return df


# Fenêtres de rolling et valeurs de remplissage neutres (du notebook 02)
ROLLING_WINDOWS = [5, 10, 20, 50]

FILL_NEUTRAL = {
    'avg_GSAE': 0.0, 'avg_xGF_pct': 0.5, 'avg_HDcf': 0.5, 'avg_top_line_xGF': 0.5,
    'avg_corsi': 0.5, 'avg_panic_score': 0.0, 'avg_star_impact': 0.0,
    'avg_net_takeaways': 0.0, 'avg_pp': 0.0, 'avg_pk': 0.0,
}

COLS_TO_ROLL = {
    'GSAE': 'avg_GSAE', 'xGF_pct': 'avg_xGF_pct', 'HDcf_pct': 'avg_HDcf',
    'top_line_xGF': 'avg_top_line_xGF', 'corsi_eff': 'avg_corsi',
    'panic_score': 'avg_panic_score', 'star_impact': 'avg_star_impact',
    'net_takeaways': 'avg_net_takeaways',
    'pp_xGF_per_min': 'avg_pp', 'pk_xGA_per_min': 'avg_pk',
}


class NHLAggregator:
    """
    Reconstruit le dataset agrégé NHL depuis les CSVs bruts Moneypuck.

    Args:
        data_dir : dossier contenant les CSVs (all_teams.csv, goalies_*, etc.)
        verbose  : log de progression
    """

    def __init__(self, data_dir: str = 'data', verbose: bool = True):
        self.data_dir = Path(data_dir)
        self.verbose = verbose

    def _path(self, name: str) -> Path:
        return self.data_dir / name

    def _log(self, msg: str):
        if self.verbose:
            print(msg)

    def _read_concat(self, category: str) -> pd.DataFrame:
        """
        Concatène TOUS les fichiers d'une catégorie présents dans data_dir.

        Détecte automatiquement via glob :
          - le fichier historique multi-saisons : {category}_2008_2024.csv
          - chaque fichier mono-saison : {category}_2025.csv, _2026.csv, ...

        Ainsi, quand une nouvelle saison arrive (ex: skaters_2026.csv ajouté
        par le downloader), elle est intégrée sans modifier le code.
        Déduplication par (gameId, playerTeam/team) après concat.
        """
        files = sorted(self.data_dir.glob(f'{category}_*.csv'))
        if not files:
            raise FileNotFoundError(
                f"Aucun fichier '{category}_*.csv' trouvé dans {self.data_dir}/"
            )
        self._log(f"   {category}: {len(files)} fichier(s) — "
                  f"{[f.name for f in files]}")
        frames = [pd.read_csv(f) for f in files]
        df = pd.concat(frames, ignore_index=True)

        # Dédup si un même match apparaît dans 2 fichiers (chevauchement saisons)
        key_cols = [c for c in ['gameId', 'playerTeam', 'team', 'situation']
                    if c in df.columns]
        if 'gameId' in df.columns and len(key_cols) > 1:
            df = df.drop_duplicates(subset=key_cols, keep='last')
        return df

    # ─────────────────────────────────────────────── Étape 1 : Gardiens
    def _build_goalies(self) -> pd.DataFrame:
        self._log("🧤 Étape 1 — Gardiens...")
        df_g = self._read_concat('goalies')
        df_g = normalize_teams(df_g)
        df_g['GSAE'] = df_g['xGoals'] - df_g['goals']
        df_g = (df_g[df_g['situation'] == 'all']
                .sort_values(['gameId', 'icetime'], ascending=[True, False])
                .drop_duplicates(subset=['gameId', 'playerTeam'])
                .rename(columns={'playerTeam': 'team', 'name': 'goalie_name'}))
        self._log(f"   {len(df_g):,} entrées | GSAE moyen : {df_g['GSAE'].mean():.3f}")
        return df_g

    # ─────────────────────────────────────────────── Étape 2 : Skaters + Lignes
    def _build_skaters_lines(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        self._log("⛸️  Étape 2 — Skaters & Lignes...")
        df_s = self._read_concat('skaters')
        df_s = normalize_teams(df_s)
        df_s = df_s[df_s['situation'] == 'all'].copy()
        df_s['star_impact'] = df_s['onIce_xGoalsPercentage'] - df_s['offIce_xGoalsPercentage']
        df_s_agg = df_s.groupby(['gameId', 'playerTeam']).agg({
            'star_impact': 'mean', 'I_F_takeaways': 'sum',
            'I_F_giveaways': 'sum', 'penaltiesDrawn': 'sum',
        }).reset_index()
        df_s_agg['net_takeaways'] = df_s_agg['I_F_takeaways'] - df_s_agg['I_F_giveaways']
        df_s_agg = df_s_agg.rename(columns={'playerTeam': 'team'})
        del df_s; gc.collect()

        df_l = self._read_concat('lines')
        df_l = normalize_teams(df_l).copy()
        df_l['panic_score'] = df_l['dZoneGiveawaysAgainst'] / (df_l['icetime'] / 60 + 0.001)
        df_l_top = (df_l[df_l['iceTimeRank'] <= 2]
                    .groupby(['gameId', 'playerTeam'])
                    .agg({'xGoalsPercentage': 'mean', 'corsiPercentage': 'mean',
                          'panic_score': 'mean'})
                    .reset_index()
                    .rename(columns={'playerTeam': 'team',
                                     'xGoalsPercentage': 'top_line_xGF',
                                     'corsiPercentage': 'corsi_eff'}))
        del df_l; gc.collect()
        self._log(f"   skaters: {len(df_s_agg):,} | lignes top2: {len(df_l_top):,}")
        return df_s_agg, df_l_top

    # ─────────────────────────────────────────────── Étape 3 : Équipe + rolling
    def _build_team_rolling(self, df_g, df_s_agg, df_l_top) -> tuple[pd.DataFrame, pd.DataFrame]:
        self._log("📊 Étape 3 — Données équipe & rolling stats...")
        df_raw = pd.read_csv(self._path('all_teams.csv'))
        df_raw = normalize_teams(df_raw)
        df_raw['gameDate'] = pd.to_datetime(df_raw['gameDate'], format='%Y%m%d')

        df_5v5  = df_raw[df_raw['situation'] == '5on5'].copy()
        df_all  = df_raw[df_raw['situation'] == 'all'].copy()
        df_5on4 = df_raw[df_raw['situation'] == '5on4'].copy()
        df_4on5 = df_raw[df_raw['situation'] == '4on5'].copy()

        # PP / PK
        if not df_5on4.empty:
            df_5on4['pp_xGF_per_min'] = df_5on4['xGoalsFor'] / (df_5on4['iceTime'] / 60 + 0.001)
            df_pp = df_5on4[['gameId', 'team', 'pp_xGF_per_min']]
        else:
            df_all['pp_xGF_per_min'] = df_all['xGoalsFor'] / (df_all['iceTime'] / 60 + 0.001)
            df_pp = df_all[['gameId', 'team', 'pp_xGF_per_min']]
        if not df_4on5.empty:
            df_4on5['pk_xGA_per_min'] = df_4on5['xGoalsAgainst'] / (df_4on5['iceTime'] / 60 + 0.001)
            df_pk = df_4on5[['gameId', 'team', 'pk_xGA_per_min']]
        else:
            df_all['pk_xGA_per_min'] = df_all['xGoalsAgainst'] / (df_all['iceTime'] / 60 + 0.001)
            df_pk = df_all[['gameId', 'team', 'pk_xGA_per_min']]

        # won_game + stress + days_rest
        df_all['won_game'] = (df_all['goalsFor'] > df_all['goalsAgainst']).astype(int)
        df_all = df_all.sort_values(['team', 'gameDate'])
        df_all['prev_date'] = df_all.groupby('team')['gameDate'].shift(1)
        df_all['days_rest'] = (df_all['gameDate'] - df_all['prev_date']).dt.days
        df_all['is_back_to_back'] = (df_all['days_rest'] == 1).astype(int)
        df_all['stress_score'] = df_all.groupby('team')['is_back_to_back'].transform(
            lambda x: x.shift(1).rolling(3, min_periods=1).sum()).fillna(0)
        df_all['goalsFor_m'] = df_all['goalsFor']
        df_all['goalsAgainst_m'] = df_all['goalsAgainst']
        df_all['xGF_m'] = df_all['xGoalsFor']
        df_all['xGA_m'] = df_all['xGoalsAgainst']
        df_all['days_rest_capped'] = df_all['days_rest'].fillna(7).clip(0, 7)
        df_all['goals_per_game'] = df_all['goalsFor_m']

        # Fusion
        df = pd.merge(df_5v5, df_l_top, on=['gameId', 'team'], how='left')
        df = pd.merge(df, df_s_agg[['gameId', 'team', 'star_impact', 'net_takeaways', 'penaltiesDrawn']],
                      on=['gameId', 'team'], how='left')
        df = pd.merge(df, df_g[['gameId', 'team', 'goalie_name', 'GSAE']],
                      on=['gameId', 'team'], how='left')
        df = pd.merge(df, df_pp, on=['gameId', 'team'], how='left')
        df = pd.merge(df, df_pk, on=['gameId', 'team'], how='left')
        df = pd.merge(df, df_all[['gameId', 'team', 'won_game', 'stress_score', 'is_back_to_back',
                                  'goalsFor_m', 'goalsAgainst_m', 'xGF_m', 'xGA_m',
                                  'days_rest_capped', 'goals_per_game']],
                      on=['gameId', 'team'], how='left')

        df['days_rest'] = df['days_rest_capped'].fillna(7)
        df['avg_goals_per_game_10'] = df.groupby('team')['goals_per_game'].transform(
            lambda x: x.shift(1).rolling(10, min_periods=2).mean()).fillna(2.85)
        df['pp_xGF_per_min'] = df['pp_xGF_per_min'].fillna(0)
        df['pk_xGA_per_min'] = df['pk_xGA_per_min'].fillna(0)
        df['xGF_pct'] = df['xGoalsFor'] / (df['xGoalsFor'] + df['xGoalsAgainst'] + 0.001)
        df['HDcf_pct'] = df['highDangerShotsFor'] / (
            df['highDangerShotsFor'] + df['highDangerShotsAgainst'] + 0.001)
        df = df.sort_values(['team', 'gameDate'])

        # PDO glissant (ratio de sommes)
        self._log("   ⏳ Rolling multi-fenêtres (5/10/20/50)...")
        for window in ROLLING_WINDOWS:
            mp = max(2, window // 3)
            s_gf = df.groupby('team')['goalsFor_m'].transform(
                lambda x, w=window, m=mp: x.shift(1).rolling(w, min_periods=m).sum())
            s_xgf = df.groupby('team')['xGF_m'].transform(
                lambda x, w=window, m=mp: x.shift(1).rolling(w, min_periods=m).sum())
            s_ga = df.groupby('team')['goalsAgainst_m'].transform(
                lambda x, w=window, m=mp: x.shift(1).rolling(w, min_periods=m).sum())
            s_xga = df.groupby('team')['xGA_m'].transform(
                lambda x, w=window, m=mp: x.shift(1).rolling(w, min_periods=m).sum())
            df[f'avg_pdo_{window}'] = (s_gf / (s_xgf + 0.001) + s_xga / (s_ga + 0.001)).fillna(2.0)

        # Rolling classique
        for col, prefix in COLS_TO_ROLL.items():
            for window in ROLLING_WINDOWS:
                mp = max(2, window // 3)
                df[f'{prefix}_{window}'] = df.groupby('team')[col].transform(
                    lambda x, w=window, m=mp: x.shift(1).rolling(w, min_periods=m).mean()
                ).fillna(FILL_NEUTRAL.get(prefix, 0.0))

        df['Forme_3_matchs'] = df.groupby('team')['won_game'].transform(
            lambda x: x.shift(1).rolling(3, min_periods=1).mean()).fillna(0.5)
        df['Forme_5_matchs'] = df.groupby('team')['won_game'].transform(
            lambda x: x.shift(1).rolling(5, min_periods=1).mean()).fillna(0.5)
        df['momentum'] = df['Forme_3_matchs'] - df['Forme_5_matchs']

        self._log(f"   Rolling OK — {len(df):,} lignes × {len(df.columns)} colonnes")
        return df, df_all

    # ─────────────────────────────────────────────── Étape 4 : Table finale
    def _build_final(self, df: pd.DataFrame, df_all: pd.DataFrame) -> pd.DataFrame:
        self._log("⚔️  Étape 4 — Table finale Home vs Away + diffs...")
        df_home = df[df['home_or_away'] == 'HOME'].add_suffix('_home')
        df_away = df[df['home_or_away'] == 'AWAY'].add_suffix('_away')
        df_final = pd.merge(df_home, df_away, left_on='gameId_home', right_on='gameId_away')

        new_cols = {}
        new_cols['impact_goalie_home'] = (df_final['avg_xGF_pct_10_home']
                                          + df_final['avg_GSAE_10_home'] * 0.12)
        new_cols['impact_goalie_away'] = (df_final['avg_xGF_pct_10_away']
                                          + df_final['avg_GSAE_10_away'] * 0.12)
        for feat in ['xGF_pct', 'HDcf', 'corsi', 'star_impact', 'net_takeaways',
                     'top_line_xGF', 'pp', 'pk', 'pdo', 'panic_score']:
            ch, ca = f'avg_{feat}_10_home', f'avg_{feat}_10_away'
            if ch in df_final.columns and ca in df_final.columns:
                new_cols[f'diff_{feat}'] = df_final[ch] - df_final[ca]
        new_cols['diff_goalie_impact'] = new_cols['impact_goalie_home'] - new_cols['impact_goalie_away']
        new_cols['diff_forme'] = df_final['Forme_5_matchs_home'] - df_final['Forme_5_matchs_away']
        new_cols['diff_momentum'] = df_final['momentum_home'] - df_final['momentum_away']
        new_cols['diff_xGF_5'] = df_final['avg_xGF_pct_5_home'] - df_final['avg_xGF_pct_5_away']
        new_cols['diff_xGF_20'] = df_final['avg_xGF_pct_20_home'] - df_final['avg_xGF_pct_20_away']
        new_cols['diff_xGF_season'] = df_final['avg_xGF_pct_50_home'] - df_final['avg_xGF_pct_50_away']
        new_cols['diff_pp_5'] = df_final['avg_pp_5_home'] - df_final['avg_pp_5_away']
        new_cols['diff_pp_20'] = df_final['avg_pp_20_home'] - df_final['avg_pp_20_away']
        new_cols['diff_b2b'] = df_final['is_back_to_back_home'] - df_final['is_back_to_back_away']
        new_cols['diff_stress'] = df_final['stress_score_home'] - df_final['stress_score_away']
        new_cols['diff_days_rest'] = df_final['days_rest_home'] - df_final['days_rest_away']
        df_final = pd.concat([df_final, pd.DataFrame(new_cols, index=df_final.index)], axis=1)

        # Cibles
        df_scores = df_all[['gameId', 'team', 'goalsFor']].copy()
        df_final = pd.merge(df_final, df_scores.rename(columns={'goalsFor': 'finalGoals_home'}),
                            left_on=['gameId_home', 'team_home'], right_on=['gameId', 'team'])
        df_final = pd.merge(df_final, df_scores.rename(columns={'goalsFor': 'finalGoals_away'}),
                            left_on=['gameId_away', 'team_away'], right_on=['gameId', 'team'])
        df_final = df_final.drop(columns=['gameId_x', 'team_x', 'gameId_y', 'team_y'], errors='ignore')

        goals_diff = df_final['finalGoals_home'] - df_final['finalGoals_away']
        target_cols = {
            'home_team_won': np.where(goals_diff > 0, 1.0, np.where(goals_diff < 0, 0.0, 0.5)),
            'goal_diff': goals_diff,
        }
        df_final = pd.concat([df_final, pd.DataFrame(target_cols, index=df_final.index)], axis=1)
        df_final = df_final.replace([np.inf, -np.inf], np.nan).fillna(0)
        self._log(f"   df_final : {len(df_final):,} matchs × {len(df_final.columns)} colonnes")
        return df_final

    # ─────────────────────────────────────────────── Bonus : period_stats (P1)
    def _merge_period_stats(self, df_final: pd.DataFrame) -> pd.DataFrame:
        ps_path = self._path('period_stats.csv')
        if not ps_path.exists():
            self._log("ℹ️  period_stats.csv absent — pas de P1 dédié (fallback approximation).")
            return df_final
        self._log("🎯 Fusion period_stats (goals_p1)...")
        period_stats = pd.read_csv(ps_path)
        period_stats['gameId'] = pd.to_numeric(period_stats['gameId'], errors='coerce').astype('Int64')
        df_final['gameId_home'] = pd.to_numeric(df_final['gameId_home'], errors='coerce').astype('Int64')
        df_final['gameId_away'] = pd.to_numeric(df_final['gameId_away'], errors='coerce').astype('Int64')
        period_stats = period_stats.dropna(subset=['gameId'])
        period_stats = normalize_teams(period_stats)

        inter = set(period_stats['gameId'].unique()) & set(df_final['gameId_home'].dropna().unique())
        if not inter:
            self._log("   ⚠️  Aucune intersection gameId — P1 ignoré.")
            return df_final

        p1 = period_stats[period_stats['period'] == 1].copy()
        p1 = p1.rename(columns={'goals': 'goals_p1', 'xGoals': 'xGoals_p1'})
        p1 = p1[['gameId', 'team', 'goals_p1', 'xGoals_p1']]
        df_final = pd.merge(df_final,
                            p1.rename(columns={'goals_p1': 'goals_p1_home', 'xGoals_p1': 'xGoals_p1_home'}),
                            left_on=['gameId_home', 'team_home'], right_on=['gameId', 'team'], how='left')
        df_final = df_final.drop(columns=['gameId', 'team'], errors='ignore')
        df_final = pd.merge(df_final,
                            p1.rename(columns={'goals_p1': 'goals_p1_away', 'xGoals_p1': 'xGoals_p1_away'}),
                            left_on=['gameId_away', 'team_away'], right_on=['gameId', 'team'], how='left')
        df_final = df_final.drop(columns=['gameId', 'team'], errors='ignore')

        n_p1 = df_final['goals_p1_home'].notna().sum()
        self._log(f"   {n_p1:,}/{len(df_final):,} matchs ({n_p1/len(df_final):.1%}) avec P1 réelle")
        for c in ['goals_p1_home', 'goals_p1_away', 'xGoals_p1_home', 'xGoals_p1_away']:
            df_final[c] = df_final[c].fillna(1.0)
        return df_final

    # ─────────────────────────────────────────────── Orchestration
    def build(self, save: bool = True,
              output_filename: str = 'dataset_agrege_vizer_nhl.csv') -> pd.DataFrame:
        """Construit le dataset complet. Retourne df_final (et sauve si save=True)."""
        df_g = self._build_goalies()
        df_s_agg, df_l_top = self._build_skaters_lines()
        df, df_all = self._build_team_rolling(df_g, df_s_agg, df_l_top)
        df_final = self._build_final(df, df_all)
        df_final = self._merge_period_stats(df_final)

        if save:
            out = self._path(output_filename)
            df_final.to_csv(out, index=False)
            self._log(f"✅ Dataset sauvegardé : {out}")
            self._log(f"   {len(df_final):,} matchs | home win rate "
                      f"{df_final['home_team_won'].mean():.1%} | "
                      f"buts dom {df_final['finalGoals_home'].mean():.2f}")
        return df_final
