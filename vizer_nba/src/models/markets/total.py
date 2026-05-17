"""
TotalMarket — marché Over/Under du total de points.

Wrap NBATotalPredictor (XGBoost régresseur) dans le contrat MarketBase.

Particularité : un régresseur produit un nombre (le total prédit), pas une
probabilité. Pour convertir en Over/Under sur une ligne L, on suppose une
distribution gaussienne autour de la prédiction avec sigma = RMSE du modèle
sur le test set. C'est une approximation acceptable étant donné que les
résidus de modèles de scoring sont quasi-gaussiens.
"""
from __future__ import annotations

from typing import Any

import math
import pandas as pd

from vizer_core import MarketBase, MarketPrediction

from src.models.total_predictor import NBATotalPredictor


# Ligne benchmark par défaut quand on n'a pas la cote bookmaker
# (utilisée pour calculer probabilities dans MarketPrediction).
# La ligne médiane NBA 2024-25 tourne autour de 225.
DEFAULT_OU_LINE: float = 225.0


def _normal_cdf(z: float) -> float:
    """CDF d'une normale standard, sans dépendre de scipy (pour rester léger)."""
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def over_under_probabilities(
    predicted_total: float,
    line: float,
    sigma: float,
) -> tuple[float, float]:
    """
    Calcule (p_over, p_under) pour une ligne donnée, en supposant
    distribution gaussienne autour de la prédiction.

    Args:
        predicted_total : valeur prédite par le modèle.
        line            : ligne du bookmaker (ex: 220.5).
        sigma           : écart-type des résidus (idéalement RMSE du modèle).

    Returns:
        (p_over, p_under) — sommant à 1.0
    """
    if sigma <= 0:
        # Cas dégénéré : prédiction parfaite
        return (1.0, 0.0) if predicted_total > line else (0.0, 1.0)
    z = (line - predicted_total) / sigma
    p_under = _normal_cdf(z)
    p_over = 1.0 - p_under
    return p_over, p_under


class TotalMarket(MarketBase):
    """
    Marché Over/Under sur le total de points d'un match.

    Selections retournées par predict() (pour la ligne par défaut) :
        - 'over_<line>'  : total > line
        - 'under_<line>' : total < line
    `expected_value` contient le total prédit (régression brute).
    `metadata['sigma']` contient l'écart-type estimé (utile pour recalculer
    sur d'autres lignes via over_under_probabilities()).
    """

    name = "total"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._predictor = NBATotalPredictor(hyperparameters=self.hyperparameters)
        self._sigma: float = 0.0  # rempli après fit (RMSE du predictor)
        self._default_line: float = config.get('default_ou_line', DEFAULT_OU_LINE)

    # ----------------------------------------------------------------- fit
    def fit(
        self,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame | None = None,
        verbose: bool = True,
    ) -> dict[str, float]:
        """Entraîne le predictor interne et stocke sigma = RMSE test."""
        if test_df is None:
            test_df = train_df
        metrics = self._predictor.train(train_df, test_df, verbose=verbose)
        # Récupérer sigma depuis les métriques : on prend test_rmse car c'est
        # la meilleure estimation de l'incertitude réelle de prédiction.
        self._sigma = float(metrics.get('test_rmse', metrics.get('train_rmse', 18.0)))
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
        Prédit le total et calcule les probas Over/Under pour la ligne par défaut.

        Args:
            home, away : abréviations 3 lettres.
            context    : DOIT contenir 'features_row'. Peut aussi contenir 'line'
                         pour calculer les probas sur une ligne précise plutôt
                         que la ligne par défaut.
        """
        if not self._is_fitted:
            raise RuntimeError(f"{type(self).__name__} non entraîné. Appeler fit() d'abord.")

        if context is None or 'features_row' not in context:
            raise ValueError(
                "TotalMarket.predict requiert context={'features_row': pd.DataFrame, "
                "[optionnel: 'line': float]}"
            )

        row = context['features_row']
        line = float(context.get('line', self._default_line))

        predicted_total = float(self._predictor.predict(row)[0])
        p_over, p_under = over_under_probabilities(predicted_total, line, self._sigma)

        # Confidence : à quel point on est sûr du côté
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
            expected_value=predicted_total,
            confidence=confidence,
            metadata={
                'model': 'xgboost_regressor',
                'sigma': self._sigma,
                'line_used': line,
                'home_team': home,
                'away_team': away,
            },
        )

    # ------------------------------- helper pour cotes multi-lignes
    def predict_for_line(
        self,
        home: str,
        away: str,
        line: float,
        context: dict[str, Any],
    ) -> MarketPrediction:
        """Convenience : prédit pour une ligne précise (sans toucher au default)."""
        ctx = dict(context)
        ctx['line'] = line
        return self.predict(home, away, ctx)

    # ------------------------------------------------ accès interne (debug)
    @property
    def predictor(self) -> NBATotalPredictor:
        return self._predictor

    @property
    def sigma(self) -> float:
        return self._sigma
