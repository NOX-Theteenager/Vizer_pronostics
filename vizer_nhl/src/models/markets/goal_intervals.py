"""
GoalIntervalsMarket — Intervalles de buts NHL (5 buckets exclusifs).

Le marché propose 5 sélections couvrant tous les totaux possibles :
    '0-2'  : 0, 1 ou 2 buts au total
    '3-4'  : 3 ou 4 buts
    '5-6'  : 5 ou 6 buts  (intervalle modal en NHL, ~30-35%)
    '7-8'  : 7 ou 8 buts
    '9+'   : 9 buts ou plus

Calcul (sous indépendance Poisson home/away) :
    X_h + X_a ~ Poisson(λ_h + λ_a)
    P(bucket [a,b]) = sum_{k=a..b} poisson.pmf(k, λ_total)

Plus utile pour le pari que les valeurs exactes car les bookmakers proposent
ces intervalles avec des cotes attractives (souvent 2.5-5.0).

Service requis : 'poisson' (NHLPoissonEngine).
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd
from scipy.stats import poisson

from vizer_core import MarketBase, MarketPrediction

from ...models.poisson_engine import NHLPoissonEngine


# Buckets standards de marché NHL
INTERVALS: list[tuple[str, int, int]] = [
    ('0-2', 0, 2),
    ('3-4', 3, 4),
    ('5-6', 5, 6),
    ('7-8', 7, 8),
    ('9+',  9, 20),   # 9+ couvre jusqu'à un cap pratique (rarissime au-delà)
]


def compute_interval_probas(
    lambda_total: float,
    intervals: list[tuple[str, int, int]] = INTERVALS,
) -> dict[str, float]:
    """
    Calcule la proba de chaque intervalle de buts.

    Pour chaque [a, b] : P(a <= total <= b) = poisson.cdf(b, λ) - poisson.cdf(a-1, λ).
    Pour le bucket dernier '9+', on prend P(total >= 9) = poisson.sf(8, λ).
    """
    result: dict[str, float] = {}
    last_idx = len(intervals) - 1
    for i, (label, lo, hi) in enumerate(intervals):
        if i == last_idx:
            # Dernier bucket : prend tout le reste
            result[label] = float(poisson.sf(lo - 1, lambda_total))
        else:
            p_hi = float(poisson.cdf(hi, lambda_total))
            p_lo_minus = float(poisson.cdf(lo - 1, lambda_total)) if lo > 0 else 0.0
            result[label] = p_hi - p_lo_minus

    # Normaliser (le cumul peut très légèrement dépasser 1 selon le cap)
    total = sum(result.values())
    if total > 0:
        result = {k: v / total for k, v in result.items()}
    return result


class GoalIntervalsMarket(MarketBase):
    """
    Marché Intervalles de buts NHL.

    Selections : '0-2', '3-4', '5-6', '7-8', '9+'.
    """

    name = "goal_intervals"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._engine: Optional[NHLPoissonEngine] = None

    def fit(
        self,
        train_df: pd.DataFrame,
        test_df: Optional[pd.DataFrame] = None,
        verbose: bool = True,
        services: Optional[dict[str, Any]] = None,
    ) -> dict[str, float]:
        if services is None or 'poisson' not in services:
            raise ValueError("GoalIntervalsMarket requiert services={'poisson': NHLPoissonEngine}")
        engine = services['poisson']
        if not isinstance(engine, NHLPoissonEngine):
            raise TypeError("services['poisson'] doit être NHLPoissonEngine")
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
            raise ValueError("GoalIntervalsMarket.predict requiert context={'features_row': DataFrame}")

        features_row = context['features_row']
        lam_h_arr, lam_a_arr = self._engine.predict_lambdas(features_row)
        lambda_home = float(lam_h_arr[0])
        lambda_away = float(lam_a_arr[0])
        lambda_total = lambda_home + lambda_away

        probas = compute_interval_probas(lambda_total)

        # Confidence : le bucket modal est rarement > 35% en NHL
        top_bucket = max(probas, key=probas.get)
        top_proba = probas[top_bucket]
        if top_proba >= 0.40:
            confidence = "high"
        elif top_proba >= 0.30:
            confidence = "medium"
        else:
            confidence = "low"

        return MarketPrediction(
            market_name=self.name,
            probabilities=probas,
            expected_value=lambda_total,
            confidence=confidence,
            metadata={
                'model': 'poisson_independent',
                'lambda_home': lambda_home,
                'lambda_away': lambda_away,
                'lambda_total': lambda_total,
                'modal_bucket': top_bucket,
                'modal_proba': top_proba,
                'home_team': home,
                'away_team': away,
            },
        )
