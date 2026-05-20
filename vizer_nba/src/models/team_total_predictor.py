"""
TeamTotalPredictor — Régresseur XGB pour les points d'une équipe seule.

Hérite de NBATotalPredictor pour réutiliser exclude_cols (anti-leakage strict),
mais change la target :
    - side='home' → target = HOME_PTS
    - side='away' → target = AWAY_PTS

Le pipeline d'entraînement et de calibration sigma est identique à NBATotalPredictor.
"""
from __future__ import annotations

import pandas as pd
from typing import Tuple

from src.models.total_predictor import NBATotalPredictor


class TeamTotalPredictor(NBATotalPredictor):
    """
    Régresseur XGB sur les points d'une équipe seule (home ou away).

    Réutilise les exclude_cols et l'early stopping de NBATotalPredictor
    pour éviter les leakages — les colonnes HOME_PTS et AWAY_PTS sont
    déjà exclues des features (elles auraient été des leaks pour le total
    aussi), on récupère juste celle qu'on prédit comme y.
    """

    def __init__(self, side: str = 'home', hyperparameters: dict = None):
        if side not in ('home', 'away'):
            raise ValueError(f"side doit être 'home' ou 'away', reçu {side!r}")
        super().__init__(hyperparameters=hyperparameters)
        self.side = side
        self.target_col = 'HOME_PTS' if side == 'home' else 'AWAY_PTS'

    def prepare_features(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
        """
        Réutilise les exclude_cols du parent (anti-leakage strict), change la target.
        """
        # On exploite la logique du parent qui exclut tout ce qu'il faut,
        # puis on remplace y par la colonne ciblée.
        X, _ = super().prepare_features(df)
        if self.target_col not in df.columns:
            raise KeyError(
                f"Colonne target '{self.target_col}' absente du DataFrame. "
                f"Colonnes disponibles : {list(df.columns)[:10]}..."
            )
        y = df[self.target_col].copy()
        return X, y
