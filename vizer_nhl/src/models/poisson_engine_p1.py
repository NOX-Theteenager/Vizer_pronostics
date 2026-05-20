"""
NHLPoissonEngineP1 — Modèle Poisson NHL pour la première période.

Deux modes de fonctionnement :

  1. MODE 'dedicated' : si le dataset contient `goals_p1_home/away`,
     entraîne 2 XGB count:poisson dédiés sur les buts P1 réels.
     C'est le mode RECOMMANDÉ (plus précis car la dynamique P1 diffère
     du jeu complet : moins de buts, équipes "tâtent" l'adversaire).

  2. MODE 'fallback' : si pas de data P1, référence un NHLPoissonEngine
     full-game existant et applique le ratio empirique P1 = 30%.
     λ_p1 = λ_total × 0.30 (validé sur 29 000 matchs : P1 = 29.7% des buts).

Le mode est détecté automatiquement au fit().
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from xgboost import XGBRegressor

from .poisson_engine import NHLPoissonEngine


# Validé sur ~29 000 matchs NHL 2008-2025 (notebook 02b)
P1_GOAL_RATIO_EMPIRICAL: float = 0.30


@dataclass
class PoissonP1EngineMetrics:
    """Métriques sortie du training P1."""
    mode: str  # 'dedicated' ou 'fallback'
    n_train: int
    n_val: int
    n_test: int
    # MAE par équipe (présentes uniquement en mode dedicated)
    mae_p1_home_test: Optional[float] = None
    mae_p1_away_test: Optional[float] = None
    mae_p1_total_test: Optional[float] = None
    lambda_p1_home_mean: float = 0.0
    lambda_p1_away_mean: float = 0.0
    p1_ratio_used: float = P1_GOAL_RATIO_EMPIRICAL
    n_features: int = 0
    best_iter_home: Optional[int] = None
    best_iter_away: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'mode': self.mode,
            'n_train': self.n_train,
            'n_val': self.n_val,
            'n_test': self.n_test,
            'mae_p1_home_test': self.mae_p1_home_test,
            'mae_p1_away_test': self.mae_p1_away_test,
            'mae_p1_total_test': self.mae_p1_total_test,
            'lambda_p1_home_mean': self.lambda_p1_home_mean,
            'lambda_p1_away_mean': self.lambda_p1_away_mean,
            'p1_ratio_used': self.p1_ratio_used,
            'n_features': self.n_features,
            'best_iter_home': self.best_iter_home,
            'best_iter_away': self.best_iter_away,
        }


class NHLPoissonEngineP1:
    """
    Service Poisson P1 NHL avec auto-détection du mode.

    Args:
        xgb_params               : hyperparams XGB pour mode 'dedicated'
        val_fraction             : fraction du train pour early stopping
        early_stopping           : patience early stopping
        p1_ratio_fallback        : ratio P1/total pour mode 'fallback' (défaut 0.30)
        target_p1_home_col       : nom de la colonne cible P1 home
        target_p1_away_col       : nom de la colonne cible P1 away
        verbose                  : log progression
    """

    def __init__(
        self,
        xgb_params: Optional[Dict] = None,
        val_fraction: float = 0.15,
        early_stopping: Optional[int] = 30,
        p1_ratio_fallback: float = P1_GOAL_RATIO_EMPIRICAL,
        target_p1_home_col: str = 'goals_p1_home',
        target_p1_away_col: str = 'goals_p1_away',
        verbose: bool = True,
    ):
        defaults = {
            'objective': 'count:poisson',
            'n_estimators': 800,
            'max_depth': 3,
            'learning_rate': 0.02,
            'subsample': 0.85,
            'colsample_bytree': 0.85,
            'reg_alpha': 0.3,
            'reg_lambda': 1.5,
            'random_state': 42,
        }
        params = {**defaults, **(xgb_params or {})}
        params['objective'] = 'count:poisson'
        self.xgb_params = params

        self.val_fraction = val_fraction
        self.early_stopping = early_stopping
        self.p1_ratio = p1_ratio_fallback
        self.target_p1_home_col = target_p1_home_col
        self.target_p1_away_col = target_p1_away_col
        self.verbose = verbose

        # États
        self.mode: Optional[str] = None  # 'dedicated' ou 'fallback'
        self.model_p1_home: Optional[XGBRegressor] = None
        self.model_p1_away: Optional[XGBRegressor] = None
        self.fallback_engine: Optional[NHLPoissonEngine] = None
        self.features_used: List[str] = []
        self.metrics: Optional[PoissonP1EngineMetrics] = None
        self.is_fitted: bool = False

    # ------------------------------------------------------------------ fit
    def fit(
        self,
        train_df: pd.DataFrame,
        features: List[str],
        test_df: Optional[pd.DataFrame] = None,
        fallback_engine: Optional[NHLPoissonEngine] = None,
    ) -> PoissonP1EngineMetrics:
        """
        Entraîne le service P1.

        Détection auto du mode :
          - Si `goals_p1_home` et `goals_p1_away` sont présents et non-NaN
            → mode 'dedicated' (entraîne 2 XGB)
          - Sinon → mode 'fallback' (utilise fallback_engine + ratio 0.30)

        Args:
            train_df         : DataFrame d'entraînement
            features         : liste des colonnes features
            test_df          : DataFrame de test (optionnel, pour métriques)
            fallback_engine  : NHLPoissonEngine fitted (utilisé seulement en
                               mode fallback). Si absent en mode fallback,
                               une exception est levée.
        """
        if self.verbose:
            print("📊 Entraînement NHLPoissonEngineP1")
            print("=" * 60)

        # Détection du mode
        has_p1_cols = (
            self.target_p1_home_col in train_df.columns
            and self.target_p1_away_col in train_df.columns
        )
        if has_p1_cols:
            # Vérifier que les valeurs ne sont pas toutes NaN/0
            n_valid = (
                train_df[self.target_p1_home_col].notna()
                & train_df[self.target_p1_away_col].notna()
                & (train_df[self.target_p1_home_col] + train_df[self.target_p1_away_col] > 0)
            ).sum()
            has_p1_data = n_valid >= max(100, int(0.1 * len(train_df)))
        else:
            has_p1_data = False

        if has_p1_data:
            self._fit_dedicated(train_df, features, test_df)
        else:
            if fallback_engine is None or not fallback_engine.is_fitted:
                raise ValueError(
                    "Mode 'fallback' requis (pas de données P1 dans train_df) "
                    "mais fallback_engine est manquant ou non-fitted.\n"
                    "  Solution : passer fallback_engine=NHLPoissonEngine déjà fitted."
                )
            self._fit_fallback(features, fallback_engine, test_df)

        self.features_used = features
        self.is_fitted = True
        return self.metrics

    def _fit_dedicated(
        self,
        train_df: pd.DataFrame,
        features: List[str],
        test_df: Optional[pd.DataFrame],
    ) -> None:
        """Entraîne 2 XGB count:poisson sur goals_p1_home/away."""
        self.mode = 'dedicated'
        if self.verbose:
            print(f"  Mode : DEDICATED (2 XGB count:poisson sur goals_p1_*)")

        # Tri chronologique + split val interne
        train_df = train_df.sort_values('gameDate_home').reset_index(drop=True)
        n = len(train_df)
        n_val = int(n * self.val_fraction)
        train_inner = train_df.iloc[:-n_val] if n_val > 0 else train_df
        val_inner = train_df.iloc[-n_val:] if n_val > 0 else train_df.iloc[-100:]

        X_tr = train_inner.reindex(columns=features, fill_value=0)
        y_h_tr = train_inner[self.target_p1_home_col].fillna(0).astype(float)
        y_a_tr = train_inner[self.target_p1_away_col].fillna(0).astype(float)
        X_val = val_inner.reindex(columns=features, fill_value=0)
        y_h_val = val_inner[self.target_p1_home_col].fillna(0).astype(float)
        y_a_val = val_inner[self.target_p1_away_col].fillna(0).astype(float)

        if self.verbose:
            print(f"  Train interne : {len(X_tr):,}  |  Val : {len(X_val):,}  "
                  f"|  Features : {len(features)}")

        fit_extra: Dict[str, Any] = {}
        if self.early_stopping:
            params = {**self.xgb_params, 'early_stopping_rounds': self.early_stopping}
            fit_extra['verbose'] = False
        else:
            params = dict(self.xgb_params)

        self.model_p1_home = XGBRegressor(**params)
        self.model_p1_away = XGBRegressor(**params)

        if self.verbose:
            print("🔧 Fit Poisson P1 home...")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if self.early_stopping:
                self.model_p1_home.fit(X_tr, y_h_tr, eval_set=[(X_val, y_h_val)], **fit_extra)
            else:
                self.model_p1_home.fit(X_tr, y_h_tr)

        if self.verbose:
            print("🔧 Fit Poisson P1 away...")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if self.early_stopping:
                self.model_p1_away.fit(X_tr, y_a_tr, eval_set=[(X_val, y_a_val)], **fit_extra)
            else:
                self.model_p1_away.fit(X_tr, y_a_tr)

        bi_h = getattr(self.model_p1_home, 'best_iteration', None)
        bi_a = getattr(self.model_p1_away, 'best_iteration', None)
        if self.verbose and (bi_h is not None or bi_a is not None):
            n_est = params.get('n_estimators', 800)
            print(f"  Best iter : home={bi_h}/{n_est}, away={bi_a}/{n_est}")

        # Métriques test si dispo
        mae_h = mae_a = mae_t = None
        lam_h_mean = lam_a_mean = 0.0
        n_test = 0
        if test_df is not None and len(test_df) > 0 and self.target_p1_home_col in test_df.columns:
            X_test = test_df.reindex(columns=features, fill_value=0)
            y_h_test = test_df[self.target_p1_home_col].fillna(0).astype(float)
            y_a_test = test_df[self.target_p1_away_col].fillna(0).astype(float)
            lam_h_test = self.model_p1_home.predict(X_test)
            lam_a_test = self.model_p1_away.predict(X_test)

            mae_h = float(mean_absolute_error(y_h_test, lam_h_test))
            mae_a = float(mean_absolute_error(y_a_test, lam_a_test))
            mae_t = float(mean_absolute_error(y_h_test + y_a_test, lam_h_test + lam_a_test))
            lam_h_mean = float(lam_h_test.mean())
            lam_a_mean = float(lam_a_test.mean())
            n_test = len(test_df)

            if self.verbose:
                print(f"\n📈 Test (n={n_test:,}) :")
                print(f"   MAE P1 home  : {mae_h:.3f} buts")
                print(f"   MAE P1 away  : {mae_a:.3f} buts")
                print(f"   MAE P1 total : {mae_t:.3f} buts")
                print(f"   λ P1 home mean : {lam_h_mean:.3f}")
                print(f"   λ P1 away mean : {lam_a_mean:.3f}")

        self.metrics = PoissonP1EngineMetrics(
            mode='dedicated',
            n_train=len(X_tr), n_val=len(X_val), n_test=n_test,
            mae_p1_home_test=mae_h, mae_p1_away_test=mae_a, mae_p1_total_test=mae_t,
            lambda_p1_home_mean=lam_h_mean,
            lambda_p1_away_mean=lam_a_mean,
            p1_ratio_used=1.0,  # pas utilisé en mode dedicated
            n_features=len(features),
            best_iter_home=bi_h, best_iter_away=bi_a,
        )

    def _fit_fallback(
        self,
        features: List[str],
        fallback_engine: NHLPoissonEngine,
        test_df: Optional[pd.DataFrame],
    ) -> None:
        """Mode fallback : référence le full-game engine + applique le ratio."""
        self.mode = 'fallback'
        if self.verbose:
            print(f"  Mode : FALLBACK (λ_p1 = λ_total × {self.p1_ratio})")
            print(f"  Référence : NHLPoissonEngine full-game (déjà fitted)")

        self.fallback_engine = fallback_engine

        # Métriques test approximatives
        lam_h_mean = lam_a_mean = 0.0
        n_test = 0
        if test_df is not None and len(test_df) > 0:
            X_test = test_df.reindex(columns=features, fill_value=0)
            lam_h_full, lam_a_full = fallback_engine.predict_lambdas(X_test)
            lam_p1_h = lam_h_full * self.p1_ratio
            lam_p1_a = lam_a_full * self.p1_ratio
            lam_h_mean = float(lam_p1_h.mean())
            lam_a_mean = float(lam_p1_a.mean())
            n_test = len(test_df)

            if self.verbose:
                print(f"\n📈 Test (n={n_test:,}) — λ approximés via fallback :")
                print(f"   λ P1 home mean : {lam_h_mean:.3f} (= λ_total × {self.p1_ratio})")
                print(f"   λ P1 away mean : {lam_a_mean:.3f}")

        self.metrics = PoissonP1EngineMetrics(
            mode='fallback',
            n_train=0, n_val=0, n_test=n_test,
            lambda_p1_home_mean=lam_h_mean,
            lambda_p1_away_mean=lam_a_mean,
            p1_ratio_used=self.p1_ratio,
            n_features=len(features),
        )

    # -------------------------------------------------------------- predict
    def predict_p1_lambdas(self, X: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """
        Retourne (λ_p1_home, λ_p1_away) pour une matrice de features.
        """
        if not self.is_fitted:
            raise RuntimeError("NHLPoissonEngineP1 non entraîné.")

        X_aligned = X.reindex(columns=self.features_used, fill_value=0)

        if self.mode == 'dedicated':
            lam_h = self.model_p1_home.predict(X_aligned)
            lam_a = self.model_p1_away.predict(X_aligned)
        elif self.mode == 'fallback':
            lam_h_full, lam_a_full = self.fallback_engine.predict_lambdas(X_aligned)
            lam_h = lam_h_full * self.p1_ratio
            lam_a = lam_a_full * self.p1_ratio
        else:
            raise RuntimeError(f"Mode inconnu : {self.mode}")

        return lam_h, lam_a
