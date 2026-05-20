"""
ExactScoreMarket — Top-N scores exacts NHL via Poisson conjoint.

Calcul (sous indépendance Poisson home/away) :
    P(i-j) = poisson.pmf(i, λ_h) × poisson.pmf(j, λ_a)

On retourne les N scores les plus probables (par défaut N=10), normalisés
pour sommer à 1 (le résidu de la troncature est redistribué proportionnellement).

Note : ce marché propose intrinsèquement BEAUCOUP de sélections. Les books
réels ne cotent que quelques scores (généralement Top-10). On garde la
même limite. Les sélections sont nommées '<home>-<away>' (ex: '3-2').

Service requis : 'poisson' (NHLPoissonEngine).
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd
from scipy.stats import poisson

from vizer_core import MarketBase, MarketPrediction

from ...models.poisson_engine import NHLPoissonEngine


# Borne sur les scores considérés (P(>= 8 buts pour une équipe) ≈ 0 en NHL)
EXACT_MAX_GOALS: int = 8
DEFAULT_TOP_N: int = 10


def compute_top_exact_scores(
    lambda_h: float,
    lambda_a: float,
    top_n: int = DEFAULT_TOP_N,
    max_goals: int = EXACT_MAX_GOALS,
) -> list[tuple[str, float]]:
    """
    Retourne [(score_str, probability), ...] triée par proba décroissante,
    tronquée au top_n, et normalisée (somme = 1).
    """
    ks = np.arange(max_goals + 1)
    p_h = poisson.pmf(ks, lambda_h)
    p_a = poisson.pmf(ks, lambda_a)
    joint = np.outer(p_h, p_a)  # joint[i, j] = P(X_h=i, X_a=j)

    # Lister tous les scores avec leur proba
    scores: list[tuple[str, float]] = []
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            scores.append((f'{i}-{j}', float(joint[i, j])))

    # Tri décroissant + top N
    scores.sort(key=lambda x: -x[1])
    top = scores[:top_n]

    # Normalisation sur le top (le résidu hors top est petit mais pas nul)
    total = sum(p for _, p in top)
    if total > 0:
        top = [(s, p / total) for s, p in top]
    return top


class ExactScoreMarket(MarketBase):
    """
    Marché Score exact NHL : Top-N scores avec leur probabilité.

    Selections : '0-0', '1-0', '0-1', '2-1', '3-2', ... (top_n par défaut = 10).
    """

    name = "exact_score"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._engine: Optional[NHLPoissonEngine] = None
        self._top_n: int = config.get('top_n', DEFAULT_TOP_N)
        self._max_goals: int = config.get('max_goals', EXACT_MAX_GOALS)

    def fit(
        self,
        train_df: pd.DataFrame,
        test_df: Optional[pd.DataFrame] = None,
        verbose: bool = True,
        services: Optional[dict[str, Any]] = None,
    ) -> dict[str, float]:
        if services is None or 'poisson' not in services:
            raise ValueError("ExactScoreMarket requiert services={'poisson': NHLPoissonEngine}")
        engine = services['poisson']
        if not isinstance(engine, NHLPoissonEngine):
            raise TypeError(f"services['poisson'] doit être NHLPoissonEngine")
        if not engine.is_fitted:
            raise RuntimeError("NHLPoissonEngine doit être .fit() avant injection.")
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
            raise ValueError("ExactScoreMarket.predict requiert context={'features_row': DataFrame}")

        features_row = context['features_row']
        lam_h_arr, lam_a_arr = self._engine.predict_lambdas(features_row)
        lambda_home = float(lam_h_arr[0])
        lambda_away = float(lam_a_arr[0])

        top_scores = compute_top_exact_scores(
            lambda_home, lambda_away,
            top_n=self._top_n, max_goals=self._max_goals,
        )

        probas = {score: p for score, p in top_scores}

        # Confidence : si le top-1 est > 12%, c'est high (rare en exact score)
        top_proba = top_scores[0][1] if top_scores else 0.0
        if top_proba >= 0.12:
            confidence = "high"
        elif top_proba >= 0.08:
            confidence = "medium"
        else:
            confidence = "low"

        return MarketPrediction(
            market_name=self.name,
            probabilities=probas,
            expected_value=None,
            confidence=confidence,
            metadata={
                'model': 'poisson_independent',
                'lambda_home': lambda_home,
                'lambda_away': lambda_away,
                'top_score': top_scores[0][0] if top_scores else None,
                'top_proba': top_proba,
                'top_n': self._top_n,
                'home_team': home,
                'away_team': away,
            },
        )
