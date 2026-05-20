"""
PoissonTotalPredictor — Modèle Poisson conjoint pour le total de points NBA.

Modélise deux processus Poisson indépendants via XGBoost avec
objective='count:poisson' :
    λ_home = XGBRegressor[poisson](features)    # E[HOME_PTS]
    λ_away = XGBRegressor[poisson](features)    # E[AWAY_PTS]

Pourquoi XGB Poisson plutôt que sklearn PoissonRegressor (linéaire) :
- sklearn PoissonRegressor est LINÉAIRE → λ = exp(β·X) → divergence
  catastrophique en cas de distribution shift entre train et test.
  Sur ce dataset (97 features corrélées + shift 22024→22025), λ peut
  passer de 115 sur train à 290 sur test. Inutilisable.
- XGB Poisson est NON-LINÉAIRE (arbres) → feuilles bornées → robuste aux
  features hors-range. Même hyperparams que NBATotalPredictor existant.

Avantages vs XGB régresseur classique :
- Distribution EXACTE pour le total : somme de deux Poisson indép =
  Poisson(λ_h + λ_a) → P(over L) = poisson.sf(L, λ_h+λ_a) sans approximation
  gaussienne avec sigma=RMSE.
- Distribution EXACTE pour la différence de scores via Skellam(λ_h, λ_a)
  → cross-check de la moneyline gratuit.
- Predictions toujours positives (objective Poisson) → physiquement correct.
- λ_home et λ_away accessibles individuellement → équivalent team totals.

Limitation Poisson théorique : suppose Var(X) = E[X]. Pour les scores NBA,
on a Var ≈ 145 (σ ≈ 12) vs E ≈ 112 → over-dispersion ~30%. XGB Poisson
arrive empiriquement à capturer ça par les arbres, mais une approche plus
rigoureuse serait Negative Binomial (non disponible dans XGB stock).
"""
from __future__ import annotations

import warnings
from typing import Tuple

import numpy as np
import pandas as pd
from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from src.models.total_predictor import NBATotalPredictor


class PoissonTotalPredictor(NBATotalPredictor):
    """
    Predictor Poisson conjoint pour HOME_PTS et AWAY_PTS via XGB[count:poisson].
    """

    def __init__(self, hyperparameters: dict = None):
        super().__init__(hyperparameters=hyperparameters)
        self.hyperparameters = hyperparameters or {}

        defaults = {
            'objective': 'count:poisson',
            'n_estimators': 500,
            'max_depth': 4,
            'learning_rate': 0.05,
            'random_state': 42,
            'reg_alpha': 0.5,
            'reg_lambda': 1.5,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
        }
        params = {**defaults, **self.hyperparameters}
        params['objective'] = 'count:poisson'  # forcer
        for k in ('model', 'eval_metric', 'scale_pos_weight', 'alpha', 'max_iter', 'tol'):
            params.pop(k, None)

        self._early_stopping_rounds = params.pop('early_stopping_rounds', None)
        self._val_fraction = params.pop('val_fraction', 0.15)

        self.model_home = XGBRegressor(**params)
        self.model_away = XGBRegressor(**params)
        self.model = self.model_home

    def prepare_features(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
        X, _ = super().prepare_features(df)
        y = df['HOME_PTS'].copy()
        return X, y

    def train(
        self,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
        verbose: bool = True,
    ) -> dict:
        if verbose:
            print("📊 Entraînement du modèle Poisson conjoint (XGB count:poisson)")
            print("=" * 50)
            print(f"Train: {len(train_df):,} matchs")
            print(f"Test:  {len(test_df):,} matchs")

        X_train, y_home_train = self.prepare_features(train_df)
        y_away_train = train_df['AWAY_PTS'].copy()
        X_test, y_home_test = self.prepare_features(test_df)
        y_away_test = test_df['AWAY_PTS'].copy()

        if verbose:
            print(f"Features: {X_train.shape[1]}")

        if self._early_stopping_rounds is not None:
            if 'GAME_DATE' in train_df.columns:
                sorted_idx = train_df.sort_values('GAME_DATE').index
                X_sorted = X_train.loc[sorted_idx]
                yh_sorted = y_home_train.loc[sorted_idx]
                ya_sorted = y_away_train.loc[sorted_idx]
            else:
                X_sorted, yh_sorted, ya_sorted = X_train, y_home_train, y_away_train
            n = len(X_sorted)
            n_val = int(n * self._val_fraction)
            X_tr, X_val = X_sorted.iloc[:-n_val], X_sorted.iloc[-n_val:]
            yh_tr, yh_val = yh_sorted.iloc[:-n_val], yh_sorted.iloc[-n_val:]
            ya_tr, ya_val = ya_sorted.iloc[:-n_val], ya_sorted.iloc[-n_val:]

            if verbose:
                print(f"⏱️  Early stopping activé : {len(X_tr):,} train interne / "
                      f"{len(X_val):,} val ({self._early_stopping_rounds} rounds patience)")

            params = self.model_home.get_xgb_params()
            params['early_stopping_rounds'] = self._early_stopping_rounds
            self.model_home = XGBRegressor(**params)
            self.model_away = XGBRegressor(**params)
            self.model = self.model_home

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                self.model_home.fit(X_tr, yh_tr, eval_set=[(X_val, yh_val)], verbose=False)
                self.model_away.fit(X_tr, ya_tr, eval_set=[(X_val, ya_val)], verbose=False)

            if verbose:
                bi_h = getattr(self.model_home, 'best_iteration', None)
                bi_a = getattr(self.model_away, 'best_iteration', None)
                ne = params.get('n_estimators', 500)
                print(f"   Best iter home: {bi_h} / {ne}, away: {bi_a} / {ne}")
        else:
            if verbose:
                print("🔧 Fit Poisson home...")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                self.model_home.fit(X_train, y_home_train)
            if verbose:
                print("🔧 Fit Poisson away...")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                self.model_away.fit(X_train, y_away_train)

        lam_h_train = self.model_home.predict(X_train)
        lam_a_train = self.model_away.predict(X_train)
        lam_h_test = self.model_home.predict(X_test)
        lam_a_test = self.model_away.predict(X_test)

        total_pred_train = lam_h_train + lam_a_train
        total_pred_test = lam_h_test + lam_a_test
        total_true_train = y_home_train + y_away_train
        total_true_test = y_home_test + y_away_test

        train_mae = mean_absolute_error(total_true_train, total_pred_train)
        test_mae = mean_absolute_error(total_true_test, total_pred_test)
        train_rmse = np.sqrt(mean_squared_error(total_true_train, total_pred_train))
        test_rmse = np.sqrt(mean_squared_error(total_true_test, total_pred_test))
        train_r2 = r2_score(total_true_train, total_pred_train)
        test_r2 = r2_score(total_true_test, total_pred_test)

        home_mae = mean_absolute_error(y_home_test, lam_h_test)
        away_mae = mean_absolute_error(y_away_test, lam_a_test)

        lam_h_mean = float(lam_h_test.mean())
        lam_a_mean = float(lam_a_test.mean())
        if lam_h_mean < 80 or lam_h_mean > 150 or lam_a_mean < 80 or lam_a_mean > 150:
            if verbose:
                print(f"\n⚠️  λ hors-range plausible : home={lam_h_mean:.1f}, "
                      f"away={lam_a_mean:.1f} (attendu ~110-120). Vérifier hyperparams.")

        if verbose:
            print()
            print("✅ Entraînement terminé")
            print(f"MAE train (total):  {train_mae:.2f} points")
            print(f"MAE test  (total):  {test_mae:.2f} points")
            print(f"RMSE train (total): {train_rmse:.2f} points")
            print(f"RMSE test  (total): {test_rmse:.2f} points")
            print(f"R² train:  {train_r2:.3f}")
            print(f"R² test:   {test_r2:.3f}")
            print()
            print(f"MAE test home (λ_home): {home_mae:.2f} pts")
            print(f"MAE test away (λ_away): {away_mae:.2f} pts")
            print(f"λ_home test : mean={lam_h_mean:.1f}, std={lam_h_test.std():.1f}")
            print(f"λ_away test : mean={lam_a_mean:.1f}, std={lam_a_test.std():.1f}")

        self.metrics = {
            'train_mae': train_mae,
            'test_mae': test_mae,
            'train_rmse': train_rmse,
            'test_rmse': test_rmse,
            'train_r2': train_r2,
            'test_r2': test_r2,
            'test_mae_home': home_mae,
            'test_mae_away': away_mae,
            'lambda_home_test_mean': lam_h_mean,
            'lambda_away_test_mean': lam_a_mean,
            'n_train': len(train_df),
            'n_test': len(test_df),
            'model_type': 'poisson_xgb_joint',
        }
        return self.metrics

    def predict(self, X) -> np.ndarray:
        lam_h, lam_a = self.predict_lambdas(X)
        return lam_h + lam_a

    def predict_lambdas(self, X) -> Tuple[np.ndarray, np.ndarray]:
        if isinstance(X, pd.DataFrame):
            X = X.reindex(columns=self.feature_columns, fill_value=0)
        lam_h = self.model_home.predict(X)
        lam_a = self.model_away.predict(X)
        return lam_h, lam_a
