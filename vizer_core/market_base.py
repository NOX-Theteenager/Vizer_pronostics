"""
MarketBase — Contrat d'un marché de paris.

Un marché (moneyline, total, P1, BTTS, ...) :
- Contient un ou plusieurs BasePredictor en interne.
- Prend en entrée (home, away, context) et produit une MarketPrediction.
- Sait calculer un ValueBet à partir d'une cote bookmaker.

Découplage clé :
- Le marché ne sait pas d'où viennent ses features. C'est l'orchestrateur
  (train.py, predict_today.py) qui lui passe un DataFrame déjà préparé.
- Le marché expose `name`, `enabled`, `hyperparameters` lus depuis config.yaml.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

import pandas as pd


Confidence = Literal["high", "medium", "low"]


# =============================================================================
# Dataclasses de sortie
# =============================================================================
@dataclass
class MarketPrediction:
    """
    Résultat d'une prédiction de marché pour un match donné.

    `probabilities` :
        Dict des probabilités par sélection.
        - Moneyline : {'home': 0.62, 'away': 0.38}
        - Over/Under : {'over': 0.55, 'under': 0.45}
        - Intervalles : {'0-2': 0.18, '3-4': 0.32, '5-6': 0.28, '7-8': 0.15, '9+': 0.07}

    `expected_value` :
        Valeur ponctuelle attendue, si applicable (total prédit, score exact, ...).
        None pour les marchés purement classification.

    `confidence` :
        Issue de la logique métier du marché (ex: BTTS NHL → 🟢🟡⚠️).

    `metadata` :
        Champ libre par marché. Exemples NHL : {'lambda_h': 1.6, 'lambda_a': 1.4,
        'p1_priors_used': True, 'goalie_starter_known': False}
    """
    market_name: str
    probabilities: dict[str, float]
    expected_value: float | None = None
    confidence: Confidence = "medium"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.probabilities:
            raise ValueError("MarketPrediction.probabilities ne peut être vide.")
        total = sum(self.probabilities.values())
        if not (0.99 <= total <= 1.01):
            raise ValueError(
                f"Les probabilités de '{self.market_name}' doivent sommer à 1.0 "
                f"(somme actuelle: {total:.4f})"
            )

    def top_selection(self) -> tuple[str, float]:
        """Retourne (sélection, probabilité) de la plus probable."""
        sel = max(self.probabilities, key=self.probabilities.get)
        return sel, self.probabilities[sel]


@dataclass
class ValueBet:
    """Pari à valeur détecté : edge positif après filtrage par seuil."""
    market_name: str
    selection: str
    # Avis du modèle — inchangé, c'est lui qui déclenche la sélection et que
    # l'app affiche face à la probabilité implicite.
    predicted_proba: float
    bookmaker_odds: float
    implied_proba: float
    edge: float                 # predicted - implied
    kelly_stake: float          # fraction du bankroll (déjà ajustée par kelly_factor)
    confidence: Confidence
    # Avis du modèle (identique à `predicted_proba`) et consensus de marché
    # marge retirée. Publiés pour pouvoir trancher plus tard qui avait raison :
    # sans eux, impossible de mesurer si le mélange a aidé ou nui.
    model_proba: float | None = None
    market_proba: float | None = None

    @property
    def expected_value_per_unit(self) -> float:
        """EV par unité misée : (proba × (cote - 1)) - (1 - proba)."""
        return self.predicted_proba * (self.bookmaker_odds - 1) - (1 - self.predicted_proba)


# =============================================================================
# MarketBase
# =============================================================================
class MarketBase(ABC):
    """
    Contrat d'un marché. Sous-classer dans `src/models/markets/<name>.py`.

    Convention de nom :
    - Attribut de classe `name: str` doit être unique (servira de clé dans ModelRegistry).
    - Classe nommée `<MarketName>Market` (ex: `MoneylineMarket`).
    """

    # Identifiant du marché (override obligatoire)
    name: str = ""

    def __init__(self, config: dict[str, Any]):
        """
        Args:
            config: La section `markets.<name>` de config.yaml.
                    Doit contenir au minimum `enabled` et `hyperparameters`.
        """
        if not self.name:
            raise NotImplementedError(
                f"{type(self).__name__} doit définir un attribut de classe `name`."
            )
        self._config = config
        self.hyperparameters: dict[str, Any] = config.get("hyperparameters", {})
        self._is_fitted: bool = False

    # ------------------------------------------------------- Réglages
    #
    # Lus depuis `_config` à chaque accès, et non figés en attributs au
    # moment de `__init__`.
    #
    # La raison est que ces objets sont **picklés avec le modèle**. Un
    # attribut posé dans `__init__` n'existe pas sur une instance restaurée
    # d'un pickle plus ancien : ajouter un réglage faisait planter la
    # prédiction en production avec un `AttributeError`, alors même que le
    # code et la config étaient corrects.
    #
    # En propriétés, un réglage absent de l'ancienne config retombe sur son
    # défaut au lieu de lever. Et `reconfigure()` permet d'appliquer la config
    # courante à un modèle déjà entraîné, sans réentraîner.

    @property
    def enabled(self) -> bool:
        return bool(self._config.get("enabled", False))

    @property
    def edge_threshold(self) -> float:
        return float(self._config.get("edge_threshold", 0.05))

    @property
    def kelly_factor(self) -> float:
        return float(self._config.get("kelly_factor", 0.25))

    @property
    def market_blend(self) -> float:
        """
        Confiance accordée au modèle face au consensus, pour **dimensionner la
        mise**. 1.0 = on ignore le marché (comportement historique) ; en
        dessous, la probabilité qui alimente Kelly est tirée vers le prix du
        marché, donc la mise rétrécit.

        Ne sert pas à sélectionner : appliquer un seuil d'edge sur une
        probabilité mélangée ne retiendrait que les plus gros désaccords,
        c'est-à-dire précisément ceux que la mesure montre perdants.
        """
        return float(self._config.get("market_blend", 1.0))

    @property
    def max_disagreement(self) -> float:
        """
        Écart maximal toléré entre le modèle et le consensus. Au-delà, on
        suspecte une erreur de modèle plutôt qu'une opportunité : gardien non
        annoncé, features périmées, équipe mal appariée. C'est un plafond, pas
        un plancher — contrairement au seuil d'edge.
        """
        return float(self._config.get("max_disagreement", 1.0))

    def reconfigure(self, config: dict[str, Any]) -> None:
        """
        Applique une nouvelle configuration à un marché déjà entraîné.

        Sans ça, `edge_threshold`, `kelly_factor` et même `enabled` restaient
        ceux du jour de l'entraînement : changer `config.yaml` n'avait aucun
        effet avant le réentraînement suivant, en silence. Les
        hyperparamètres, eux, ne sont pas touchés — ils ont façonné un modèle
        déjà ajusté, les relire n'aurait aucun sens.
        """
        merged = dict(self._config)
        merged.update({k: v for k, v in config.items() if k != "hyperparameters"})
        self._config = merged

    # ------------------------------------------------------------ Interface
    @abstractmethod
    def fit(self, features_df: pd.DataFrame, target_df: pd.DataFrame) -> dict[str, float]:
        """
        Entraîne le ou les predictors internes.

        Args:
            features_df : DataFrame contenant TOUTES les features nécessaires
                          + colonnes méta (game_id, season, home_team, away_team, ...).
            target_df   : DataFrame des cibles. Le marché choisit ses colonnes.

        Returns:
            Dict de métriques (idem BasePredictor).
        """
        raise NotImplementedError

    @abstractmethod
    def predict(
        self,
        home: str,
        away: str,
        context: dict[str, Any] | None = None,
    ) -> MarketPrediction:
        """
        Prédit pour un match.

        Args:
            home, away : abréviations 3 lettres.
            context    : libre, peut contenir gardiens partants (NHL),
                         repos, line-up, etc. À documenter par marché.
        """
        raise NotImplementedError

    # ---------------------------------------------------------- Value bet
    def value_bet(
        self,
        prediction: MarketPrediction,
        selection: str,
        bookmaker_odds: float,
        market_proba: float | None = None,
    ) -> ValueBet | None:
        """
        Détecte un value bet si l'edge dépasse le seuil configuré.

        Calcul de la mise Kelly :
            kelly = (proba × cote - 1) / (cote - 1)
            stake = max(0, kelly) × kelly_factor    (jamais de mise négative)

        Returns:
            ValueBet si edge ≥ edge_threshold ET sélection valide, sinon None.
        """
        if not self.enabled:
            # Un marché désactivé ne doit pas produire de pari. Ça n'allait pas
            # de soi : le détecteur n'interrogeait que la présence du marché
            # dans le registre, si bien qu'un marché mis hors service continuait
            # de publier des value bets.
            return None
        if selection not in prediction.probabilities:
            return None
        if bookmaker_odds <= 1.0:
            return None

        proba = prediction.probabilities[selection]
        implied = 1.0 / bookmaker_odds
        edge = proba - implied

        # ── Sélection : sur l'avis du modèle, pas sur un mélange ──────────
        if edge < self.edge_threshold:
            return None

        # Plafond de désaccord. Le prix du marché agrège ce que le modèle ne
        # voit pas : gardien confirmé, blessure de dernière minute, argent
        # informé. Un modèle peut être bien calibré sur l'ensemble des matchs
        # et se tromper précisément là où il s'écarte le plus du marché —
        # c'est ce que montre l'historique publié, où l'erreur grandit avec le
        # désaccord. Au-delà du plafond, on lit ça comme un bug, pas une
        # aubaine.
        if market_proba is not None and (proba - market_proba) > self.max_disagreement:
            return None

        # ── Dimensionnement : là, le marché compte ────────────────────────
        # La mise suit une probabilité tirée vers le consensus. Parier sur
        # l'avis du modèle tout en misant comme si le marché n'existait pas
        # revient à doubler la confiance accordée à la seule source qu'on
        # n'a pas encore prouvée.
        if market_proba is not None and 0.0 <= self.market_blend < 1.0:
            sizing = self.market_blend * proba + (1 - self.market_blend) * market_proba
        else:
            sizing = proba

        kelly_raw = (sizing * bookmaker_odds - 1) / (bookmaker_odds - 1)
        kelly_stake = max(0.0, kelly_raw) * self.kelly_factor

        return ValueBet(
            market_name=self.name,
            selection=selection,
            predicted_proba=proba,
            bookmaker_odds=bookmaker_odds,
            implied_proba=implied,
            edge=edge,
            kelly_stake=kelly_stake,
            confidence=prediction.confidence,
            model_proba=proba,
            market_proba=market_proba,
        )

    # ----------------------------------------------------------- Helpers
    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    def __repr__(self) -> str:
        status = "fitted" if self._is_fitted else "not fitted"
        flag = "✓" if self.enabled else "✗"
        return f"<{type(self).__name__} name='{self.name}' enabled={flag} {status}>"
