"""
TotalPoissonMarket — Marché Total Over/Under via modèle Poisson conjoint.

Alternative à TotalMarket (XGB régresseur). Cohabite dans le registre :
- `total`         : XGB régresseur + sigma gaussien (rapide, plus flexible)
- `total_poisson` : Poisson(λ_h + λ_a) (distribution exacte, plus interprétable)

Pour activer, mettre `markets.total_poisson.enabled: true` dans config.yaml.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
from scipy.stats import poisson, skellam

from vizer_core import MarketBase, MarketPrediction

from src.models.poisson_total_predictor import PoissonTotalPredictor


DEFAULT_OU_LINE: float = 225.0


def poisson_over_under_probabilities(
    lambda_total: float,
    line: float,
) -> tuple[float, float]:
    """
    Probas O/U EXACTES pour un total ~ Poisson(λ_total) et une ligne fractionnaire.

    Pour line = X.5 :
        p_over  = P(total >= X+1) = poisson.sf(X, λ)
        p_under = P(total <= X)   = poisson.cdf(X, λ)

    Pour line entière (rare aux US — lignes typiques en .5) :
        on traite line comme un "no action" → on retourne p_over/p_under en
        excluant le push : P(total > line) et P(total < line).
    """
    # Cas push : line entière exacte
    if line == int(line):
        line_int = int(line)
        p_over_strict = poisson.sf(line_int, lambda_total)
        p_under_strict = poisson.cdf(line_int - 1, lambda_total)
        # Normaliser (exclure le push pour ne pas que les probas dépassent 1)
        denom = p_over_strict + p_under_strict
        if denom > 0:
            return float(p_over_strict / denom), float(p_under_strict / denom)
        return 0.5, 0.5

    # Cas standard : line = X.5
    line_floor = int(line)  # ex : 224 pour line=224.5
    p_over = float(poisson.sf(line_floor, lambda_total))   # P(X > line_floor)
    p_under = float(poisson.cdf(line_floor, lambda_total))  # P(X <= line_floor)
    return p_over, p_under


class TotalPoissonMarket(MarketBase):
    """
    Marché Over/Under sur le total via Poisson conjoint.

    Selections retournées par predict() (ligne par défaut) :
        - 'over_<line>'  : P(total > line)
        - 'under_<line>' : P(total < line)
    `expected_value` contient le total prédit (λ_home + λ_away).
    `metadata` contient :
        - 'lambda_home', 'lambda_away' : paramètres Poisson estimés
        - 'p_home_wins'                : proba via Skellam (cross-check moneyline)
        - 'line_used', 'model'
    """

    name = "total_poisson"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._predictor = PoissonTotalPredictor(hyperparameters=self.hyperparameters)
        self._default_line: float = config.get('default_ou_line', DEFAULT_OU_LINE)

    # ----------------------------------------------------------------- fit
    def fit(
        self,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame | None = None,
        verbose: bool = True,
    ) -> dict[str, float]:
        if test_df is None:
            test_df = train_df
        metrics = self._predictor.train(train_df, test_df, verbose=verbose)
        self._is_fitted = True
        return metrics

    # ------------------------------------------------------------- predict
    def predict(
        self,
        home: str,
        away: str,
        context: dict[str, Any] | None = None,
    ) -> MarketPrediction:
        """
        Prédit le total via λ_h + λ_a et calcule les probas O/U exactes pour
        la ligne par défaut (ou celle passée dans context['line']).

        En bonus : calcule aussi P(home wins) via Skellam(λ_h, λ_a) pour
        cross-check de la moneyline XGB (utile en debug / diagnostic).
        """
        if not self._is_fitted:
            raise RuntimeError(f"{type(self).__name__} non entraîné. Appeler fit().")

        if context is None or 'features_row' not in context:
            raise ValueError(
                "TotalPoissonMarket.predict requiert "
                "context={'features_row': pd.DataFrame, [optionnel: 'line': float]}"
            )

        row = context['features_row']
        line = float(context.get('line', self._default_line))

        lam_h_arr, lam_a_arr = self._predictor.predict_lambdas(row)
        lambda_home = float(lam_h_arr[0])
        lambda_away = float(lam_a_arr[0])
        lambda_total = lambda_home + lambda_away

        p_over, p_under = poisson_over_under_probabilities(lambda_total, line)

        # P(home wins) via Skellam (en bonus, pas exposé comme proba principale)
        # P(home_pts > away_pts) = P(Z > 0) où Z = X - Y ~ Skellam(λ_h, λ_a)
        p_home_wins = float(1 - skellam.cdf(0, lambda_home, lambda_away))

        # Confidence
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
                'model': 'poisson_joint',
                'lambda_home': lambda_home,
                'lambda_away': lambda_away,
                'lambda_total': lambda_total,
                'p_home_wins': p_home_wins,  # cross-check vs moneyline
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

    @property
    def predictor(self) -> PoissonTotalPredictor:
        return self._predictor
