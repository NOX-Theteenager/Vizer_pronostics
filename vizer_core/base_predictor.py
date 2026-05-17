"""
BasePredictor — Contrat abstrait pour tout modèle ML sous-jacent.

Un BasePredictor wrap un modèle ML (XGBoost, LightGBM, Poisson, ordinal, ...) et
expose une interface uniforme. Un marché (MarketBase) peut contenir un ou
plusieurs BasePredictor.

Exemple d'utilisation côté implémentation NBA :

    class XGBWinPredictor(BasePredictor):
        def __init__(self, hyperparameters: dict):
            super().__init__(hyperparameters)
            self._model = XGBClassifier(**hyperparameters)

        def fit(self, X_train, y_train, X_test=None, y_test=None):
            self._model.fit(X_train, y_train)
            self._feature_names = list(X_train.columns)
            return self._compute_metrics(X_test, y_test) if X_test is not None else {}

        def predict(self, X):
            return self._model.predict(X[self._feature_names])

        def predict_proba(self, X):
            return self._model.predict_proba(X[self._feature_names])
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd


class BasePredictor(ABC):
    """
    Contrat d'un modèle ML.

    Sous-classes attendues :
    - Implémentent `fit`, `predict`.
    - Implémentent `predict_proba` SI le modèle est probabiliste (classification
      ou régression Poisson). Sinon laissent l'erreur par défaut.
    - Stockent leurs feature names dans `self._feature_names` lors du `fit`.
    """

    def __init__(self, hyperparameters: dict[str, Any] | None = None):
        self.hyperparameters: dict[str, Any] = hyperparameters or {}
        self._feature_names: list[str] = []
        self._is_fitted: bool = False

    # ------------------------------------------------------------------ API
    @abstractmethod
    def fit(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series | np.ndarray,
        X_test: pd.DataFrame | None = None,
        y_test: pd.Series | np.ndarray | None = None,
    ) -> dict[str, float]:
        """
        Entraîne le modèle.

        Returns:
            Dict de métriques (clé = nom métrique, valeur = score).
            Exemple: {'auc_train': 0.65, 'auc_test': 0.61, 'accuracy_test': 0.58}
            Retourner un dict vide si pas de test set.
        """
        raise NotImplementedError

    @abstractmethod
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Prédiction ponctuelle (classe ou valeur scalaire)."""
        raise NotImplementedError

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """
        Probabilités. À surcharger uniquement si le modèle est probabiliste.

        Convention :
        - Classification binaire : shape (n, 2), colonne 1 = proba classe positive
        - Classification multiclasse : shape (n, k)
        - Régression Poisson : shape (n, K) où K = bornes des classes, ou (n,)
          si on retourne juste λ.
        """
        raise NotImplementedError(
            f"{type(self).__name__} ne fournit pas de prédiction probabiliste. "
            "Surcharger predict_proba si applicable."
        )

    def feature_importances(self) -> dict[str, float]:
        """
        Importance des features pour debug. Retourne {} par défaut.
        À surcharger si le modèle expose cette information.
        """
        return {}

    # ------------------------------------------------------------ Propriétés
    @property
    def feature_names(self) -> list[str]:
        """Noms des features attendues en entrée. Disponibles après fit."""
        if not self._is_fitted:
            raise RuntimeError(
                f"{type(self).__name__} n'a pas encore été entraîné. "
                "Appeler fit() avant d'accéder à feature_names."
            )
        return list(self._feature_names)

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    # --------------------------------------------------------- Persistance
    def save(self, path: str | Path) -> None:
        """Sauvegarde le predictor entier via joblib."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @classmethod
    def load(cls, path: str | Path) -> "BasePredictor":
        """Charge un predictor sauvegardé."""
        return joblib.load(Path(path))

    # ----------------------------------------------------------- Utilities
    def _validate_features(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Vérifie et réordonne les colonnes pour matcher l'ordre d'entraînement.
        Lève une erreur explicite si des features manquent.
        """
        if not self._is_fitted:
            raise RuntimeError(f"{type(self).__name__} pas entraîné.")
        missing = set(self._feature_names) - set(X.columns)
        if missing:
            raise ValueError(
                f"Features manquantes en prédiction : {sorted(missing)}"
            )
        return X[self._feature_names]
