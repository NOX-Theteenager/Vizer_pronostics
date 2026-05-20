"""
NHLFeatureEngineer — Applique les transformations terminales NHL.

Part du df_final déjà rolling-aggregated (post-notebook 02) et applique :
  1. RECOVERED_DIFFS  : diffs de features récupérées (avg_HDcf_10_home - _away ...)
  2. MULTI_WINDOW_DIFFS : diffs multi-fenêtres 5/10/20/50
  3. Elo dynamique calculé inline (zéro leakage)
  4. Interactions (goalie × xGF, forme × xGF)
  5. Filtre des dead features (variance < 1e-10)

C'est le pendant de la cellule "Chargement & Feature Engineering" du notebook
03_Entrainement.ipynb, sous forme modulaire et réutilisable.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from ..utils import (
    RECOVERED_DIFFS,
    MULTI_WINDOW_DIFFS,
    CANDIDATE_FEATURES,
    compute_elo_column,
    compute_team_elos,
    safe_diff,
)


class NHLFeatureEngineer:
    """
    Applique les transformations finales sur le df_final agrégé.

    Args:
        elo_k          : taux d'apprentissage Elo (défaut: 20)
        elo_home_bonus : bonus domicile en pts Elo (défaut: 35)
        elo_base       : rating initial Elo (défaut: 1500)
        verbose        : log de progression
    """

    def __init__(
        self,
        elo_k: float = 20.0,
        elo_home_bonus: float = 35.0,
        elo_base: float = 1500.0,
        verbose: bool = True,
    ):
        self.elo_k = elo_k
        self.elo_home_bonus = elo_home_bonus
        self.elo_base = elo_base
        self.verbose = verbose
        # États post-fit (utilisables à l'inférence)
        self.features_used: List[str] = []
        self.features_dead: List[str] = []
        self.team_elos: dict[str, float] = {}

    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Applique toutes les transformations sur le DataFrame d'entraînement.

        Returns:
            df enrichi avec les diffs, Elo, interactions. Les colonnes brutes
            _home/_away sont conservées (pour permettre re-calculs ad-hoc).
        """
        if self.verbose:
            print("🔧 NHL Feature Engineering...")

        df = df.copy()
        n_before = len(df)

        # --- 1. RECOVERED_DIFFS ---
        added = []
        for col_h, col_a, new_name in RECOVERED_DIFFS:
            result = safe_diff(df, col_h, col_a)
            if result is not None and new_name not in df.columns:
                df[new_name] = result
                added.append(new_name)
        if self.verbose and added:
            print(f"  ✓ Recovered diffs : {added}")

        # --- 2. MULTI_WINDOW_DIFFS ---
        added = []
        for col_h, col_a, new_name in MULTI_WINDOW_DIFFS:
            result = safe_diff(df, col_h, col_a)
            if result is not None and new_name not in df.columns:
                df[new_name] = result
                added.append(new_name)
        if self.verbose and added:
            print(f"  ✓ Multi-window diffs : {len(added)} ajoutés")

        # --- 3. Elo dynamique ---
        if self.verbose:
            print(f"  📊 Calcul Elo (k={self.elo_k}, home_bonus={self.elo_home_bonus})...")
        df_elo = compute_elo_column(
            df,
            k=self.elo_k,
            base=self.elo_base,
            home_bonus=self.elo_home_bonus,
        )
        # Si l'Elo n'a pas pu être calculé (df vide), skip
        if not df_elo.empty:
            df = df.merge(df_elo, on='gameId_home', how='left')
            df['elo_home'] = df['elo_home'].fillna(self.elo_base)
            df['elo_away'] = df['elo_away'].fillna(self.elo_base)
            df['diff_elo'] = df['elo_home'] - df['elo_away']
            # Sauvegarder ratings finaux pour l'inférence
            self.team_elos = compute_team_elos(
                df, k=self.elo_k, base=self.elo_base, home_bonus=self.elo_home_bonus
            )
            if self.verbose:
                print(f"  ✓ Elo calculé : {len(self.team_elos)} équipes "
                      f"(range {min(self.team_elos.values()):.0f} - "
                      f"{max(self.team_elos.values()):.0f})")

        # --- 4. Interactions ---
        if 'diff_goalie_impact' in df.columns and 'diff_xGF_pct' in df.columns:
            df['interaction_goalie_xgf'] = df['diff_goalie_impact'] * df['diff_xGF_pct']
        if 'diff_forme' in df.columns and 'diff_xGF_pct' in df.columns:
            df['interaction_forme_xgf'] = df['diff_forme'] * df['diff_xGF_pct']

        # --- 5. Features finales = candidates qui existent ET ont de la variance ---
        features_present = [f for f in CANDIDATE_FEATURES if f in df.columns]
        self.features_dead = [
            f for f in features_present
            if df[f].var() < 1e-10
        ]
        self.features_used = [f for f in features_present if f not in self.features_dead]

        if self.verbose:
            print(f"  ✓ Features finales : {len(self.features_used)}")
            if self.features_dead:
                print(f"  ⚠️  Features mortes désactivées : {self.features_dead}")

        # Sanity check
        assert len(df) == n_before, "feature engineering ne doit pas filtrer de lignes"

        return df

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Applique les transformations sur un dataset d'inférence (sans recalculer
        les statistiques). Elo doit être déjà mergé ou injecté par l'appelant.

        Pour l'inférence prod, c'est plus subtil : les rolling stats devraient
        être issues du dernier état connu. Pour cette V1, on suppose que df
        contient déjà les colonnes _home/_away nécessaires.
        """
        df = df.copy()

        # Diffs (idempotents : skip si déjà présents)
        for col_h, col_a, new_name in RECOVERED_DIFFS + MULTI_WINDOW_DIFFS:
            if new_name not in df.columns:
                result = safe_diff(df, col_h, col_a)
                if result is not None:
                    df[new_name] = result

        # diff_elo : utiliser les Elo stockés en mémoire
        if 'diff_elo' not in df.columns and self.team_elos:
            df['elo_home'] = df['team_home'].map(self.team_elos).fillna(self.elo_base)
            df['elo_away'] = df['team_away'].map(self.team_elos).fillna(self.elo_base)
            df['diff_elo'] = df['elo_home'] - df['elo_away']

        # Interactions
        if 'diff_goalie_impact' in df.columns and 'diff_xGF_pct' in df.columns:
            df['interaction_goalie_xgf'] = df['diff_goalie_impact'] * df['diff_xGF_pct']
        if 'diff_forme' in df.columns and 'diff_xGF_pct' in df.columns:
            df['interaction_forme_xgf'] = df['diff_forme'] * df['diff_xGF_pct']

        return df

    def get_feature_matrix(self, df: pd.DataFrame) -> pd.DataFrame:
        """Retourne X = df[self.features_used] avec colonnes manquantes à 0."""
        return df.reindex(columns=self.features_used, fill_value=0)
