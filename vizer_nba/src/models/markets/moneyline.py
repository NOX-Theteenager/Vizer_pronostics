"""
MoneylineMarket — marché de victoire (home vs away).

Wrap NBAMatchPredictor (XGBoost calibré) dans le contrat vizer_core.MarketBase.
La logique d'entraînement et de prédiction reste dans NBAMatchPredictor ; ce
fichier ne fait que l'adapter à l'API standardisée.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from vizer_core import MarketBase, MarketPrediction

from src.models.win_predictor import NBAMatchPredictor


# Bornes au-delà desquelles on refuse d'annoncer une probabilité.
#
# La calibration isotonique produit des paliers, et aux extrémités elle recopie
# la valeur du palier d'entraînement — qui peut valoir exactement 0 ou 1.
# Mesuré le 27/10/2026 sur le modèle en service : **41 affiches sur 870
# annonçaient 0 % ou 100 %**, et une telle prédiction a déjà été publiée (une
# entrée sur 45 depuis l'ouverture de la saison). Aucun match de NBA n'est
# certain ; les affiches les plus déséquilibrées se négocient autour de 95 %.
#
# Ce n'est pas une correction du modèle — son classement reste inchangé — mais
# un refus d'énoncer une certitude qui n'existe pas. Deux effets concrets :
# l'application n'affiche plus « 100 % de chances », et le calcul de Kelly ne
# peut plus voir un pari sans risque. Le plafond de désaccord avec le marché
# écartait déjà ces cas en pratique, mais il les écartait par accident — rien
# ne garantissait qu'il reste en place, ni qu'il couvre les autres marchés.
#
# Le NHL n'a pas ce défaut (min 0,20, max 0,76 sur 2 772 prédictions
# publiées), d'où une borne posée ici et non dans `vizer_core`.
PROBA_FLOOR = 0.02
PROBA_CEIL = 0.98


def _no_certainty(p: float) -> float:
    """Ramène une probabilité dans les bornes du dicible."""
    return min(max(p, PROBA_FLOOR), PROBA_CEIL)


class MoneylineMarket(MarketBase):
    """
    Marché Moneyline : prédit le vainqueur d'un match.

    Selections retournées par predict() :
        - 'home' : équipe à domicile gagne
        - 'away' : équipe à l'extérieur gagne
    """

    name = "moneyline"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._predictor = NBAMatchPredictor(
            calibrate=config.get('calibrate', True),
            hyperparameters=self.hyperparameters,
        )

    # ----------------------------------------------------------------- fit
    def fit(
        self,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame | None = None,
        verbose: bool = True,
    ) -> dict[str, float]:
        """
        Entraîne le predictor interne.

        Args:
            train_df : DataFrame contenant features + target HOME_WIN.
            test_df  : DataFrame de test pour calcul des métriques. Si None,
                       les métriques test seront calculées sur train (peu fiable).
        """
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
        Prédit le vainqueur pour un match.

        Args:
            home, away : abréviations 3 lettres (ex: 'LAL', 'GSW').
            context    : DOIT contenir `features_row` (pd.DataFrame d'une ligne
                         avec les features attendues par le predictor).
                         Cette responsabilité incombe au caller (predict_today,
                         predict_json) — pour l'instant, en attendant que
                         FeatureBuilder soit en place.
        """
        if not self._is_fitted:
            raise RuntimeError(f"{type(self).__name__} non entraîné. Appeler fit() d'abord.")

        if context is None or 'features_row' not in context:
            raise ValueError(
                "MoneylineMarket.predict requiert context={'features_row': pd.DataFrame}. "
                "Construire la ligne via engineer.create_features puis filtrer."
            )

        row = context['features_row']
        probas = self._predictor.predict_proba(row)
        # XGBClassifier renvoie [proba_classe_0, proba_classe_1]
        # Classe 1 = HOME_WIN (cf. win_predictor.prepare_features → y = HOME_WIN)
        # Borné : la calibration isotonique peut rendre exactement 0 ou 1.
        p_home = _no_certainty(float(probas[0][1]))
        p_away = 1.0 - p_home

        # Confidence : marge par rapport à 50/50
        margin = abs(p_home - 0.5)
        if margin >= 0.20:
            confidence = "high"
        elif margin >= 0.10:
            confidence = "medium"
        else:
            confidence = "low"

        return MarketPrediction(
            market_name=self.name,
            probabilities={'home': p_home, 'away': p_away},
            confidence=confidence,
            metadata={
                'model': 'xgboost_calibrated',
                'home_team': home,
                'away_team': away,
            },
        )

    # ------------------------------------------------ accès interne (debug)
    @property
    def predictor(self) -> NBAMatchPredictor:
        """Accès au predictor sous-jacent pour debug / introspection."""
        return self._predictor
