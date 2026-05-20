"""
TeamTotalMarket — marchés Over/Under sur les points d'une équipe seule.

Deux markets sont exposés :
    - HomeTeamTotalMarket : Over/Under sur HOME_PTS
    - AwayTeamTotalMarket : Over/Under sur AWAY_PTS

Mécanique identique à TotalMarket (régresseur XGB + sigma calibré = RMSE),
appliquée à une équipe seule. La ligne par défaut est plus basse (~112 pour
le home, ~110 pour l'away — moitié du total typique avec léger biais HCA).

Permet de prendre des paris team total chez les bookmakers (très liquides
sur certains marchés US, et parfois +EV car moins suivis que le total global).
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from vizer_core import MarketBase, MarketPrediction

from src.models.team_total_predictor import TeamTotalPredictor
# Réutilise la formule O/U gaussienne déjà testée
from src.models.markets.total import over_under_probabilities


# Lignes médianes NBA 2024-25 : home ~112.5, away ~110.5 (léger HCA)
DEFAULT_HOME_LINE: float = 112.5
DEFAULT_AWAY_LINE: float = 110.5


class _TeamTotalMarketBase(MarketBase):
    """
    Base partagée par HomeTeamTotalMarket et AwayTeamTotalMarket.

    Les sous-classes définissent :
        - name      (str)        : identifiant du market dans le registre
        - side      ('home'/'away'): quelle équipe prédire
        - team_label (str)       : pour les logs ('home' ou 'away')
        - default_line (float)   : ligne par défaut quand pas de cote bookmaker
    """

    # À overrider par les sous-classes
    name: str = "_team_total_base"
    side: str = "home"
    team_label: str = "home"
    default_line: float = 112.5

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._predictor = TeamTotalPredictor(
            side=self.side,
            hyperparameters=self.hyperparameters,
        )
        self._sigma: float = 0.0
        self._default_line: float = config.get('default_ou_line', self.default_line)

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
        # sigma : team_total a moins de variance que le total global
        # (sigma typique 12-14 vs 18 pour le total)
        self._sigma = float(metrics.get('test_rmse', metrics.get('train_rmse', 13.0)))
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
        Prédit les points de l'équipe (home ou away selon self.side) et calcule
        les probas Over/Under pour la ligne par défaut.

        Args:
            home, away : abréviations 3 lettres (informatif).
            context    : DOIT contenir 'features_row'. Optionnellement 'line'.
        """
        if not self._is_fitted:
            raise RuntimeError(f"{type(self).__name__} non entraîné. Appeler fit() d'abord.")

        if context is None or 'features_row' not in context:
            raise ValueError(
                f"{self.name}.predict requiert "
                "context={'features_row': pd.DataFrame, [optionnel: 'line': float]}"
            )

        row = context['features_row']
        line = float(context.get('line', self._default_line))

        predicted_team_pts = float(self._predictor.predict(row)[0])
        p_over, p_under = over_under_probabilities(predicted_team_pts, line, self._sigma)

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
            expected_value=predicted_team_pts,
            confidence=confidence,
            metadata={
                'model': 'xgboost_regressor',
                'sigma': self._sigma,
                'line_used': line,
                'home_team': home,
                'away_team': away,
                'side': self.side,
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
        """Convenience : prédit pour une ligne précise."""
        ctx = dict(context)
        ctx['line'] = line
        return self.predict(home, away, ctx)

    # ------------------------------------------------ accès interne (debug)
    @property
    def predictor(self) -> TeamTotalPredictor:
        return self._predictor

    @property
    def sigma(self) -> float:
        return self._sigma


class HomeTeamTotalMarket(_TeamTotalMarketBase):
    """Over/Under sur les points de l'équipe à domicile."""
    name = "home_team_total"
    side = "home"
    team_label = "home"
    default_line = DEFAULT_HOME_LINE


class AwayTeamTotalMarket(_TeamTotalMarketBase):
    """Over/Under sur les points de l'équipe à l'extérieur."""
    name = "away_team_total"
    side = "away"
    team_label = "away"
    default_line = DEFAULT_AWAY_LINE
