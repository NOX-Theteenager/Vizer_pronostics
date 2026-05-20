"""
P1WinnerMarket — Vainqueur de la 1ère période NHL (3-way).

Selections : 'home_lead', 'tied', 'away_lead' (état à la fin de la P1).

Calcul (sous indépendance Poisson home/away en P1) :
    P(home_lead) = Σ P(X_h=i, X_a=j) pour i > j
    P(tied)      = Σ P(X_h=i, X_a=j) pour i == j
    P(away_lead) = Σ P(X_h=i, X_a=j) pour i < j

avec P(X_h=i, X_a=j) = poisson.pmf(i, λ_p1_h) × poisson.pmf(j, λ_p1_a).

Borne pratique : on tronque à max_k=8 buts par équipe en P1 (largement
suffisant, P(8+ buts en P1) ≈ 0). Le résidu est redistribué proportionnellement.

Service requis : 'poisson_p1' (NHLPoissonEngineP1 pré-entraîné).
"""
from __future__ import annotations

from typing import Any, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.stats import poisson

from vizer_core import MarketBase, MarketPrediction

from ...models.poisson_engine_p1 import NHLPoissonEngineP1


# Max buts par équipe en P1 (statistiquement P(8+) ≈ 0)
P1_MAX_K: int = 8


def compute_p1_3way_probas(
    lambda_p1_h: float,
    lambda_p1_a: float,
    max_k: int = P1_MAX_K,
) -> Tuple[float, float, float]:
    """
    Calcule (P(home_lead), P(tied), P(away_lead)) à la fin de la P1.

    Vectorisé via numpy outer product sur les pmf Poisson.
    """
    ks = np.arange(max_k + 1)
    p_h = poisson.pmf(ks, lambda_p1_h)
    p_a = poisson.pmf(ks, lambda_p1_a)
    joint = np.outer(p_h, p_a)  # joint[i, j] = P(X_h=i, X_a=j)

    # Convention : i = ligne (home), j = colonne (away)
    p_home_lead = float(np.tril(joint, k=-1).sum())  # i > j
    p_tied = float(np.diag(joint).sum())             # i == j
    p_away_lead = float(np.triu(joint, k=1).sum())   # i < j

    # Normalisation (résidu de la troncature à max_k)
    total = p_home_lead + p_tied + p_away_lead
    if total > 0:
        p_home_lead /= total
        p_tied /= total
        p_away_lead /= total

    return p_home_lead, p_tied, p_away_lead


class P1WinnerMarket(MarketBase):
    """
    Marché P1 winner 3-way : qui mène à la fin de la 1ère période ?

    Service requis : 'poisson_p1'.
    """

    name = "p1_winner"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._engine: Optional[NHLPoissonEngineP1] = None

    def fit(
        self,
        train_df: pd.DataFrame,
        test_df: Optional[pd.DataFrame] = None,
        verbose: bool = True,
        services: Optional[dict[str, Any]] = None,
    ) -> dict[str, float]:
        if services is None or 'poisson_p1' not in services:
            raise ValueError(
                "P1WinnerMarket requiert services={'poisson_p1': NHLPoissonEngineP1}"
            )
        engine = services['poisson_p1']
        if not isinstance(engine, NHLPoissonEngineP1):
            raise TypeError(
                f"services['poisson_p1'] doit être NHLPoissonEngineP1, "
                f"reçu {type(engine).__name__}"
            )
        if not engine.is_fitted:
            raise RuntimeError("NHLPoissonEngineP1 doit être .fit() avant injection.")

        self._engine = engine
        self._is_fitted = True
        return engine.metrics.to_dict() if engine.metrics else {}

    def predict(
        self,
        home: str,
        away: str,
        context: Optional[dict[str, Any]] = None,
    ) -> MarketPrediction:
        if not self._is_fitted or self._engine is None:
            raise RuntimeError(f"{type(self).__name__} non entraîné.")
        if context is None or 'features_row' not in context:
            raise ValueError(
                "P1WinnerMarket.predict requiert context={'features_row': DataFrame}"
            )

        features_row = context['features_row']
        lam_h_arr, lam_a_arr = self._engine.predict_p1_lambdas(features_row)
        lambda_p1_h = float(lam_h_arr[0])
        lambda_p1_a = float(lam_a_arr[0])

        p_home_lead, p_tied, p_away_lead = compute_p1_3way_probas(lambda_p1_h, lambda_p1_a)

        confidence_proba = max(p_home_lead, p_tied, p_away_lead)
        if confidence_proba >= 0.50:
            confidence = "high"
        elif confidence_proba >= 0.40:
            confidence = "medium"
        else:
            confidence = "low"

        return MarketPrediction(
            market_name=self.name,
            probabilities={
                'home_lead': p_home_lead,
                'tied': p_tied,
                'away_lead': p_away_lead,
            },
            expected_value=None,
            confidence=confidence,
            metadata={
                'model': 'poisson_p1_independent',
                'mode': self._engine.mode,
                'lambda_p1_home': lambda_p1_h,
                'lambda_p1_away': lambda_p1_a,
                'home_team': home,
                'away_team': away,
            },
        )
