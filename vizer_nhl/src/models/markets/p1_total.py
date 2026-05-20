"""
P1TotalMarket — Over/Under total de buts en 1ère période NHL.

Lignes typiques : 0.5, 1.5, 2.5 (la ligne 1.5 est la plus courante car
λ_p1_total ≈ 1.7-1.9 → match symétrique sur 1.5).

Calcul exact via convolution Poisson :
    X_h + X_a ~ Poisson(λ_p1_h + λ_p1_a)
    P(total > L) = poisson.sf(floor(L), λ_p1_total)

Service requis : 'poisson_p1' (NHLPoissonEngineP1).
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd
from scipy.stats import poisson

from vizer_core import MarketBase, MarketPrediction

from ...models.poisson_engine_p1 import NHLPoissonEngineP1


DEFAULT_P1_OU_LINE: float = 1.5


def p1_total_over_under_probas(
    lambda_p1_total: float,
    line: float,
) -> tuple[float, float]:
    """
    Probas O/U exactes pour le total P1 via Poisson somme.

    Pour line = X.5 :
        p_over  = P(total >= X+1) = poisson.sf(X, λ)
        p_under = P(total <= X)   = poisson.cdf(X, λ)

    Pour line entière (push possible) : on normalise hors-push.
    """
    if line == int(line):
        L = int(line)
        p_over_strict = float(poisson.sf(L, lambda_p1_total))
        p_under_strict = float(poisson.cdf(L - 1, lambda_p1_total))
        s = p_over_strict + p_under_strict
        if s > 0:
            return p_over_strict / s, p_under_strict / s
        return 0.5, 0.5
    L_floor = int(line)
    p_over = float(poisson.sf(L_floor, lambda_p1_total))
    p_under = float(poisson.cdf(L_floor, lambda_p1_total))
    return p_over, p_under


class P1TotalMarket(MarketBase):
    """
    Marché O/U total P1.

    Selections : 'over_<line>', 'under_<line>'.
    """

    name = "p1_total"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._engine: Optional[NHLPoissonEngineP1] = None
        self._default_line: float = config.get('default_ou_line', DEFAULT_P1_OU_LINE)

    def fit(
        self,
        train_df: pd.DataFrame,
        test_df: Optional[pd.DataFrame] = None,
        verbose: bool = True,
        services: Optional[dict[str, Any]] = None,
    ) -> dict[str, float]:
        if services is None or 'poisson_p1' not in services:
            raise ValueError(
                "P1TotalMarket requiert services={'poisson_p1': NHLPoissonEngineP1}"
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
                "P1TotalMarket.predict requiert "
                "context={'features_row': DataFrame, [optionnel: 'line': float]}"
            )

        features_row = context['features_row']
        line = float(context.get('line', self._default_line))

        lam_h_arr, lam_a_arr = self._engine.predict_p1_lambdas(features_row)
        lambda_p1_h = float(lam_h_arr[0])
        lambda_p1_a = float(lam_a_arr[0])
        lambda_p1_total = lambda_p1_h + lambda_p1_a

        p_over, p_under = p1_total_over_under_probas(lambda_p1_total, line)

        confidence_proba = max(p_over, p_under)
        if confidence_proba >= 0.65:
            confidence = "high"
        elif confidence_proba >= 0.55:
            confidence = "medium"
        else:
            confidence = "low"

        return MarketPrediction(
            market_name=self.name,
            probabilities={
                f'over_{line}': p_over,
                f'under_{line}': p_under,
            },
            expected_value=lambda_p1_total,
            confidence=confidence,
            metadata={
                'model': 'poisson_p1_independent',
                'mode': self._engine.mode,
                'lambda_p1_home': lambda_p1_h,
                'lambda_p1_away': lambda_p1_a,
                'lambda_p1_total': lambda_p1_total,
                'line_used': line,
                'home_team': home,
                'away_team': away,
            },
        )

    def predict_for_line(
        self,
        home: str,
        away: str,
        line: float,
        context: dict[str, Any],
    ) -> MarketPrediction:
        """Convenience : prédit pour une ligne précise."""
        ctx = dict(context)
        ctx['line'] = line
        return self.predict(home, away, ctx)
