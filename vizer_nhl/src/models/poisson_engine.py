"""
NHLPoissonEngine — Modèle Poisson conjoint pour buts NHL.

Décisions finalisées suite à l'analyse V5.6 des données réelles :
  - NB désactivé : var/mean ≈ 0.99 sur train (= Poisson pur)
  - Bivariate désactivé : cov(home, away) ≈ -0.16 (négative, non-modélisable)
  - On utilise l'indépendance home/away qui est théoriquement justifiée

Architecture :
  λ_h = XGBRegressor(objective='count:poisson')(features)
  λ_a = XGBRegressor(objective='count:poisson')(features)

Avantages :
  - Predictions toujours positives (objective Poisson)
  - Distribution exacte pour markets dérivés (total, BTTS, exact scores)
  - Robuste aux distribution shifts (arbres bornés)
  - Service unique injectable dans 6+ markets

Le predict_lambdas(X) retourne (λ_h, λ_a) que les markets consomment pour
calculer leurs propres probabilités analytiquement via scipy.stats.poisson.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor


@dataclass
class PoissonEngineMetrics:
    """Métriques sortie du training."""
    n_train: int
    n_val: int
    n_test: int
    # MAE par équipe (target principale)
    mae_home_test: float
    mae_away_test: float
    # MAE sur le total (pour comparer avec total_predictor classique)
    mae_total_test: float
    rmse_total_test: float
    r2_total_test: float
    # λ moyens sur test (sanity check distribution)
    lambda_home_mean: float
    lambda_away_mean: float
    n_features: int
    best_iter_home: Optional[int] = None
    best_iter_away: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'n_train': self.n_train,
            'n_val': self.n_val,
            'n_test': self.n_test,
            'mae_home_test': self.mae_home_test,
            'mae_away_test': self.mae_away_test,
            'mae_total_test': self.mae_total_test,
            'rmse_total_test': self.rmse_total_test,
            'r2_total_test': self.r2_total_test,
            'lambda_home_mean': self.lambda_home_mean,
            'lambda_away_mean': self.lambda_away_mean,
            'n_features': self.n_features,
            'best_iter_home': self.best_iter_home,
            'best_iter_away': self.best_iter_away,
            'model_type': 'poisson_xgb_independent',
        }


class NHLPoissonEngine:
    """
    Service Poisson NHL : 2 XGBRegressor avec objective='count:poisson'.

    Args:
        xgb_params       : hyperparams XGB (mêmes pour home et away)
        val_fraction     : fraction du train pour early stopping
        early_stopping   : patience early stopping (None = désactivé)
        verbose          : log de progression
    """

    def __init__(
        self,
        xgb_params: Optional[Dict] = None,
        val_fraction: float = 0.15,
        early_stopping: Optional[int] = 30,
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
        # Forcer objective Poisson (impossible à override)
        params['objective'] = 'count:poisson'
        self.xgb_params = params
        self.val_fraction = val_fraction
        self.early_stopping = early_stopping
        self.verbose = verbose

        self.model_home: Optional[XGBRegressor] = None
        self.model_away: Optional[XGBRegressor] = None
        self.features_used: List[str] = []
        self.metrics: Optional[PoissonEngineMetrics] = None
        self.is_fitted: bool = False

    def fit(
        self,
        train_df: pd.DataFrame,
        features: List[str],
        target_home_col: str = 'finalGoals_home',
        target_away_col: str = 'finalGoals_away',
        test_df: Optional[pd.DataFrame] = None,
    ) -> PoissonEngineMetrics:
        """Entraîne les 2 régresseurs Poisson en parallèle."""
        if self.verbose:
            print("📊 Entraînement NHLPoissonEngine (2 XGB count:poisson)")
            print("=" * 60)

        # Tri chronologique + split val interne
        train_df = train_df.sort_values('gameDate_home').reset_index(drop=True)
        n = len(train_df)
        n_val = int(n * self.val_fraction)
        train_inner = train_df.iloc[:-n_val] if n_val > 0 else train_df
        val_inner = train_df.iloc[-n_val:] if n_val > 0 else train_df.iloc[-100:]

        X_tr = train_inner.reindex(columns=features, fill_value=0)
        y_h_tr = train_inner[target_home_col].astype(float)
        y_a_tr = train_inner[target_away_col].astype(float)
        X_val = val_inner.reindex(columns=features, fill_value=0)
        y_h_val = val_inner[target_home_col].astype(float)
        y_a_val = val_inner[target_away_col].astype(float)

        if self.verbose:
            print(f"Train interne : {len(X_tr):,}  |  Val : {len(X_val):,}  "
                  f"|  Features : {len(features)}")

        # Construire les modèles
        fit_extra: Dict[str, Any] = {}
        if self.early_stopping:
            params = {**self.xgb_params, 'early_stopping_rounds': self.early_stopping}
            fit_extra['verbose'] = False
        else:
            params = dict(self.xgb_params)

        self.model_home = XGBRegressor(**params)
        self.model_away = XGBRegressor(**params)

        if self.verbose:
            print("🔧 Fit Poisson home...")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if self.early_stopping:
                self.model_home.fit(X_tr, y_h_tr, eval_set=[(X_val, y_h_val)], **fit_extra)
            else:
                self.model_home.fit(X_tr, y_h_tr)

        if self.verbose:
            print("🔧 Fit Poisson away...")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if self.early_stopping:
                self.model_away.fit(X_tr, y_a_tr, eval_set=[(X_val, y_a_val)], **fit_extra)
            else:
                self.model_away.fit(X_tr, y_a_tr)

        bi_h = getattr(self.model_home, 'best_iteration', None)
        bi_a = getattr(self.model_away, 'best_iteration', None)
        if self.verbose and (bi_h is not None or bi_a is not None):
            n_est = params.get('n_estimators', 800)
            print(f"  Best iter : home={bi_h}/{n_est}, away={bi_a}/{n_est}")

        self.features_used = features
        self.is_fitted = True

        # Métriques test
        if test_df is not None and len(test_df) > 0:
            X_test = test_df.reindex(columns=features, fill_value=0)
            y_h_test = test_df[target_home_col].astype(float)
            y_a_test = test_df[target_away_col].astype(float)

            lam_h_test = self.model_home.predict(X_test)
            lam_a_test = self.model_away.predict(X_test)

            total_true = y_h_test + y_a_test
            total_pred = lam_h_test + lam_a_test

            mae_home = mean_absolute_error(y_h_test, lam_h_test)
            mae_away = mean_absolute_error(y_a_test, lam_a_test)
            mae_total = mean_absolute_error(total_true, total_pred)
            rmse_total = float(np.sqrt(mean_squared_error(total_true, total_pred)))
            r2_total = float(r2_score(total_true, total_pred))
            lam_h_mean = float(lam_h_test.mean())
            lam_a_mean = float(lam_a_test.mean())

            # Sanity check : λ NHL plausibles ≈ 2.5-3.5
            if lam_h_mean < 1.0 or lam_h_mean > 5.0:
                if self.verbose:
                    print(f"⚠️  λ_home moyenne {lam_h_mean:.2f} hors plage NHL plausible (2.5-3.5)")
            if lam_a_mean < 1.0 or lam_a_mean > 5.0:
                if self.verbose:
                    print(f"⚠️  λ_away moyenne {lam_a_mean:.2f} hors plage NHL plausible (2.5-3.5)")

            if self.verbose:
                print(f"\n📈 Test (n={len(test_df):,}) :")
                print(f"   MAE home (λ_h)  : {mae_home:.3f} buts")
                print(f"   MAE away (λ_a)  : {mae_away:.3f} buts")
                print(f"   MAE total       : {mae_total:.3f} buts")
                print(f"   RMSE total      : {rmse_total:.3f} buts")
                print(f"   R² total        : {r2_total:.4f}")
                print(f"   λ_home mean     : {lam_h_mean:.3f}, std : {lam_h_test.std():.3f}")
                print(f"   λ_away mean     : {lam_a_mean:.3f}, std : {lam_a_test.std():.3f}")
        else:
            mae_home = mae_away = mae_total = rmse_total = r2_total = 0.0
            lam_h_mean = lam_a_mean = 0.0

        self.metrics = PoissonEngineMetrics(
            n_train=len(X_tr), n_val=len(X_val),
            n_test=len(test_df) if test_df is not None else 0,
            mae_home_test=float(mae_home), mae_away_test=float(mae_away),
            mae_total_test=float(mae_total),
            rmse_total_test=float(rmse_total),
            r2_total_test=float(r2_total),
            lambda_home_mean=lam_h_mean,
            lambda_away_mean=lam_a_mean,
            n_features=len(features),
            best_iter_home=bi_h, best_iter_away=bi_a,
        )
        return self.metrics

    def predict_lambdas(self, X: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """
        Retourne (λ_home_array, λ_away_array) pour une matrice de features.
        Aligne les colonnes sur self.features_used (manquantes → 0).
        """
        if not self.is_fitted:
            raise RuntimeError("NHLPoissonEngine non entraîné. Appeler fit() d'abord.")
        X_aligned = X.reindex(columns=self.features_used, fill_value=0)
        lam_h = self.model_home.predict(X_aligned)
        lam_a = self.model_away.predict(X_aligned)
        return lam_h, lam_a
