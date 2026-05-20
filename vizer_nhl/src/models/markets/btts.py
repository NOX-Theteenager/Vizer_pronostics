"""
BTTSMarket — Both Teams To Score (les deux équipes marquent ≥ 1 but).

Formule analytique exacte (sous indépendance home/away) :

    P(home marque ≥ 1) = 1 - P(home = 0) = 1 - exp(-λ_h)
    P(away marque ≥ 1) = 1 - P(away = 0) = 1 - exp(-λ_a)
    P(BTTS) = (1 - exp(-λ_h)) × (1 - exp(-λ_a))

Avec les λ_h, λ_a typiques NHL (≈ 3), P(BTTS) ≈ 90% en moyenne.
Les value bets se trouvent sur les "matchs blanchissage probable" (équipe
faible offensivement + gardien adverse en forme) où P(BTTS) descend à 75%.

Service requis : 'poisson' (NHLPoissonEngine pré-entraîné).
"""
from __future__ import annotations

import math
from typing import Any, Optional

import pandas as pd

from vizer_core import MarketBase, MarketPrediction

from ...models.poisson_engine import NHLPoissonEngine


class BTTSMarket(MarketBase):
    """
    Marché BTTS NHL.

    Selections : 'yes', 'no'.
    """

    name = "btts"

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
            raise ValueError("BTTSMarket requiert services={'poisson': NHLPoissonEngine}.")
        engine = services['poisson']
        if not isinstance(engine, NHLPoissonEngine):
            raise TypeError(
                f"services['poisson'] doit être NHLPoissonEngine, reçu {type(engine).__name__}"
            )
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
            raise ValueError("BTTSMarket.predict requiert context={'features_row': DataFrame}")

        features_row = context['features_row']
        lam_h_arr, lam_a_arr = self._engine.predict_lambdas(features_row)
        lambda_home = float(lam_h_arr[0])
        lambda_away = float(lam_a_arr[0])

        # P(BTTS) = P(home ≥ 1) × P(away ≥ 1)
        p_h_score = 1.0 - math.exp(-lambda_home)
        p_a_score = 1.0 - math.exp(-lambda_away)
        p_yes = p_h_score * p_a_score
        p_no = 1.0 - p_yes

        confidence_proba = max(p_yes, p_no)
        if confidence_proba >= 0.85:
            confidence = "high"
        elif confidence_proba >= 0.70:
            confidence = "medium"
        else:
            confidence = "low"

        return MarketPrediction(
            market_name=self.name,
            probabilities={'yes': p_yes, 'no': p_no},
            expected_value=None,
            confidence=confidence,
            metadata={
                'model': 'poisson_independent',
                'lambda_home': lambda_home,
                'lambda_away': lambda_away,
                'p_home_scores': p_h_score,
                'p_away_scores': p_a_score,
                'home_team': home,
                'away_team': away,
            },
        )
