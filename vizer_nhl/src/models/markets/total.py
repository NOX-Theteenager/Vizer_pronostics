"""
TotalMarket — Over/Under total de buts NHL via Poisson conjoint.

Pattern service-backed : consomme NHLPoissonEngine pré-entraîné.

Théorème exploité :
    Si X_h ~ Poisson(λ_h) et X_a ~ Poisson(λ_a) indépendants,
    alors X_h + X_a ~ Poisson(λ_h + λ_a).

Donc :
    P(total > L) = 1 - poisson.cdf(floor(L), λ_h + λ_a)

Pour les lignes typiques NHL (5.5, 6.5) on a une distribution exacte sans
approximation gaussienne.
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd
from scipy.stats import poisson

from vizer_core import MarketBase, MarketPrediction

from ...models.poisson_engine import NHLPoissonEngine


DEFAULT_OU_LINE: float = 5.5


def poisson_over_under_probas(
    lambda_total: float,
    line: float,
) -> tuple[float, float]:
    """
    Probas O/U exactes via Poisson somme.

    Pour line = X.5 (cas standard NHL) :
        p_over  = P(total >= X+1) = poisson.sf(X, λ)
        p_under = P(total <= X)   = poisson.cdf(X, λ)
        somme = 1

    Pour line entière (rare) :
        On exclut le push, normalise les probas O/U strictes.
    """
    if line == int(line):
        # Ligne entière → normaliser hors-push
        L = int(line)
        p_over_strict = float(poisson.sf(L, lambda_total))      # > L
        p_under_strict = float(poisson.cdf(L - 1, lambda_total)) # < L
        s = p_over_strict + p_under_strict
        if s > 0:
            return p_over_strict / s, p_under_strict / s
        return 0.5, 0.5
    # Ligne fractionnaire .5
    L_floor = int(line)
    p_over = float(poisson.sf(L_floor, lambda_total))
    p_under = float(poisson.cdf(L_floor, lambda_total))
    return p_over, p_under


class TotalMarket(MarketBase):
    """
    Marché Over/Under total de buts NHL.

    Service requis : 'poisson' (NHLPoissonEngine pré-entraîné).
    Selections retournées : 'over_<line>', 'under_<line>'.
    """

    name = "total"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._engine: Optional[NHLPoissonEngine] = None
        self._default_line: float = config.get('default_ou_line', DEFAULT_OU_LINE)

    def fit(
        self,
        train_df: pd.DataFrame,
        test_df: Optional[pd.DataFrame] = None,
        verbose: bool = True,
        services: Optional[dict[str, Any]] = None,
    ) -> dict[str, float]:
        if services is None or 'poisson' not in services:
            raise ValueError(
                "TotalMarket requiert services={'poisson': NHLPoissonEngine fitted}."
            )
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
            raise ValueError(
                "TotalMarket.predict requiert "
                "context={'features_row': DataFrame, [optionnel: 'line': float]}"
            )

        features_row = context['features_row']
        line = float(context.get('line', self._default_line))

        lam_h_arr, lam_a_arr = self._engine.predict_lambdas(features_row)
        lambda_home = float(lam_h_arr[0])
        lambda_away = float(lam_a_arr[0])
        lambda_total = lambda_home + lambda_away

        p_over, p_under = poisson_over_under_probas(lambda_total, line)

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
            expected_value=lambda_total,
            confidence=confidence,
            metadata={
                'model': 'poisson_independent',
                'lambda_home': lambda_home,
                'lambda_away': lambda_away,
                'lambda_total': lambda_total,
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
