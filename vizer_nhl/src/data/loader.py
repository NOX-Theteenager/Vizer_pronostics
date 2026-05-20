"""
NHLDataLoader — charge le dataset NHL agrégé (post-notebook02).

Le pipeline d'agrégation Moneypuck (skaters, goalies, team rolling stats,
period data) reste dans les notebooks 01-02b. Cette classe consomme le
df_final.csv produit en sortie du notebook 02.

Colonnes attendues dans df_final.csv :
    Méta :
        gameId_home, gameId_away, gameDate_home, gameDate_away
        team_home, team_away
    Cibles :
        home_team_won (0/1, SO ratio à 0.5 doit être déjà arrondi)
        finalGoals_home, finalGoals_away
        (optionnel) goals_p1_home, goals_p1_away
    Features _home/_away (utilisées pour calculer les diffs) :
        avg_xGF_pct_{5,10,20,50}_*, avg_pp_{5,10,20}_*, avg_pk_10_*
        avg_HDcf_10_*, avg_panic_score_10_*, avg_corsi_10_*, avg_pdo_10_*
        avg_top_line_xGF_10_*, avg_GSAE_10_*
        Forme_5_matchs_*, momentum_*
        is_back_to_back_*, days_rest_*, stress_score_*
    Diffs déjà calculés (présents par défaut dans le df_final) :
        diff_xGF_pct, diff_top_line_xGF, diff_pp, diff_pk, diff_forme,
        diff_b2b, diff_HDcf, diff_panic_score, diff_pdo, diff_momentum, ...
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


REQUIRED_META_COLS = [
    'gameId_home', 'gameDate_home', 'team_home', 'team_away',
    'home_team_won', 'finalGoals_home', 'finalGoals_away',
]


class NHLDataLoader:
    """
    Charge le dataset NHL agrégé.

    Args:
        data_dir : Chemin du dossier data/ (défaut: 'data')
        filename : Nom du CSV agrégé (défaut: 'dataset_agrege_vizer_nhl.csv',
                   c'est-à-dire OUTPUT_DATASET du notebook 02_Agregation)
    """

    def __init__(
        self,
        data_dir: str = 'data',
        filename: str = 'dataset_agrege_vizer_nhl.csv',
    ):
        self.data_dir = Path(data_dir)
        self.filename = filename
        self._path = self.data_dir / filename

    def load(
        self,
        exclude_anomalous_seasons: bool = True,
        excluded_years: tuple[int, ...] = (2013, 2020),
    ) -> pd.DataFrame:
        """
        Charge le DataFrame, applique les nettoyages standards et filtre les
        saisons anormales (lock-out, COVID) par défaut.

        Args:
            exclude_anomalous_seasons : si True, retire les années de la liste
                excluded_years (par défaut 2013 = lock-out, 2020 = COVID bubble).
        """
        if not self._path.exists():
            raise FileNotFoundError(
                f"Dataset NHL introuvable : {self._path}\n"
                f"  Lance d'abord les notebooks 01_Maintenance et 02_Agregation\n"
                f"  pour produire {self.filename} dans {self.data_dir}/"
            )

        df = pd.read_csv(self._path)
        df = df.replace([np.inf, -np.inf], np.nan)

        # Vérification colonnes critiques
        missing = [c for c in REQUIRED_META_COLS if c not in df.columns]
        if missing:
            raise ValueError(
                f"Colonnes manquantes dans {self.filename} : {missing}\n"
                f"  Le CSV doit être généré par 02_Agregation.ipynb."
            )

        # Cible : home_team_won (round si SO = 0.5)
        df['home_team_won'] = (
            pd.to_numeric(df['home_team_won'], errors='coerce')
              .round(0)
              .astype('Int64')
        )
        df = df.dropna(subset=['home_team_won'])
        df['home_team_won'] = df['home_team_won'].astype(int)

        # Date au format datetime
        df['gameDate_home'] = pd.to_datetime(df['gameDate_home'])

        # Filtrer saisons anormales (V5.4)
        if exclude_anomalous_seasons and excluded_years:
            n_before = len(df)
            df = df[~df['gameDate_home'].dt.year.isin(excluded_years)].copy()
            n_removed = n_before - len(df)
            if n_removed > 0:
                print(f"  ℹ Exclusion saisons anomalous {excluded_years} : "
                      f"-{n_removed} matchs ({n_removed/n_before:.1%})")

        # Fillna sur les autres colonnes (zéros pour les features manquantes)
        df = df.fillna(0)

        return df.reset_index(drop=True)

    def split_chronological(
        self,
        df: pd.DataFrame,
        train_until_year: int,
        test_year: Optional[int] = None,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Split temporel : train sur tous les matchs jusqu'à l'année donnée
        (incluse), test sur l'année suivante.

        Args:
            df               : DataFrame chargé
            train_until_year : dernière année (incluse) pour le train
            test_year        : année de test (par défaut: train_until_year + 1)

        Returns:
            (train_df, test_df)
        """
        if test_year is None:
            test_year = train_until_year + 1

        df = df.sort_values('gameDate_home').reset_index(drop=True)
        years = df['gameDate_home'].dt.year

        train_mask = years <= train_until_year
        test_mask = years == test_year

        train_df = df[train_mask].reset_index(drop=True)
        test_df = df[test_mask].reset_index(drop=True)

        return train_df, test_df

    @staticmethod
    def has_period1_data(df: pd.DataFrame) -> bool:
        """True si goals_p1_home et goals_p1_away sont présents."""
        return 'goals_p1_home' in df.columns and 'goals_p1_away' in df.columns
