"""
P1BTTSMarket — Les deux équipes marquent en 1ère période NHL.

Formule analytique exacte (sous indépendance Poisson P1) :

    P(home marque en P1)  = 1 - exp(-λ_p1_h)
    P(away marque en P1)  = 1 - exp(-λ_p1_a)
    P(P1 BTTS)            = P(home marque) × P(away marque)

Avec λ_p1 typique ≈ 0.85 par équipe, on a :
    P(home marque) = 1 - e^-0.85 ≈ 0.57
    P(P1 BTTS) ≈ 0.32

C'est un marché à low-probability mais avec des odds attractives chez les
books (~2.7-3.0). Value bets sur les matchs offensifs où les deux teams
ont λ_p1 > 1.0.

Service requis : 'poisson_p1' (NHLPoissonEngineP1).
"""
from __future__ import annotations

import math
from typing import Any, Optional

import pandas as pd

from vizer_core import MarketBase, MarketPrediction

from ...models.poisson_engine_p1 import NHLPoissonEngineP1


class P1BTTSMarket(MarketBase):
    """
    Marché BTTS P1.

    Selections : 'yes', 'no'.
    """

    name = "p1_btts"

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
                "P1BTTSMarket requiert services={'poisson_p1': NHLPoissonEngineP1}"
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
            raise ValueError("P1BTTSMarket.predict requiert context={'features_row': DataFrame}")

        features_row = context['features_row']
        lam_h_arr, lam_a_arr = self._engine.predict_p1_lambdas(features_row)
        lambda_p1_h = float(lam_h_arr[0])
        lambda_p1_a = float(lam_a_arr[0])

        p_h_score = 1.0 - math.exp(-lambda_p1_h)
        p_a_score = 1.0 - math.exp(-lambda_p1_a)
        p_yes = p_h_score * p_a_score
        p_no = 1.0 - p_yes

        # Confidence ajustée pour P1 BTTS (P_yes est rarement > 50%)
        confidence_proba = max(p_yes, p_no)
        if confidence_proba >= 0.75:
            confidence = "high"
        elif confidence_proba >= 0.60:
            confidence = "medium"
        else:
            confidence = "low"

        return MarketPrediction(
            market_name=self.name,
            probabilities={'yes': p_yes, 'no': p_no},
            expected_value=None,
            confidence=confidence,
            metadata={
                'model': 'poisson_p1_independent',
                'mode': self._engine.mode,
                'lambda_p1_home': lambda_p1_h,
                'lambda_p1_away': lambda_p1_a,
                'p_p1_home_scores': p_h_score,
                'p_p1_away_scores': p_a_score,
                'home_team': home,
                'away_team': away,
            },
        )
