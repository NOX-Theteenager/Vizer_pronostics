"""
NHLMoneylineEngine — Modèle de prédiction P(home_wins) pour le NHL.

Reprend l'architecture éprouvée du notebook 03_Entrainement V5.6 :
  1. Entraîne XGBClassifier et LGBMClassifier en parallèle (early stopping)
  2. Choisit le meilleur sur AUC val (pour l'ensemble pondéré)
  3. Calibre via TemperatureScalingCalibrator (1 paramètre, AUC préservée)

À l'inférence, retourne directement P(home_wins) calibrée.
Conçu comme "service" injecté dans le ModelRegistry : un seul fit alimente
plusieurs marchés (moneyline en V1, +OT/SO et close_game dans le futur).
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler

from ..utils import TemperatureScalingCalibrator


@dataclass
class MoneylineEngineMetrics:
    """Métriques sortie du training."""
    n_train: int
    n_val: int
    n_test: int
    auc_xgb_val: float
    auc_lgb_val: float
    best_model_name: str
    auc_test: float
    accuracy_test: float
    brier_raw_test: float
    brier_calibrated_test: float
    temperature: float
    features_used: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'n_train': self.n_train,
            'n_val': self.n_val,
            'n_test': self.n_test,
            'auc_xgb_val': self.auc_xgb_val,
            'auc_lgb_val': self.auc_lgb_val,
            'best_model_name': self.best_model_name,
            'auc_test': self.auc_test,
            'accuracy_test': self.accuracy_test,
            'brier_raw_test': self.brier_raw_test,
            'brier_calibrated_test': self.brier_calibrated_test,
            'temperature': self.temperature,
            'n_features': len(self.features_used),
        }


class NHLMoneylineEngine:
    """
    Service de prédiction P(home_wins) NHL.

    Args:
        xgb_params : hyperparams XGBClassifier
        lgb_params : hyperparams LGBMClassifier
        val_fraction : fraction du train pour l'early stopping + calibration
        verbose : log de progression
    """

    def __init__(
        self,
        xgb_params: Optional[Dict] = None,
        lgb_params: Optional[Dict] = None,
        val_fraction: float = 0.15,
        verbose: bool = True,
    ):
        # Hyperparams par défaut (raisonnables, ajustés vs notebook)
        default_xgb = {
            'n_estimators': 500,
            'max_depth': 4,
            'learning_rate': 0.05,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'reg_alpha': 0.5,
            'reg_lambda': 1.5,
            'random_state': 42,
            'eval_metric': 'logloss',
            'objective': 'binary:logistic',
        }
        default_lgb = {
            'n_estimators': 500,
            'max_depth': 4,
            'learning_rate': 0.05,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'random_state': 42,
            'objective': 'binary',
            'verbosity': -1,
        }
        self.xgb_params = {**default_xgb, **(xgb_params or {})}
        self.lgb_params = {**default_lgb, **(lgb_params or {})}
        self.val_fraction = val_fraction
        self.verbose = verbose

        # Composants
        self.scaler: Optional[StandardScaler] = None
        self.xgb_model = None
        self.lgb_model = None
        self.best_name: str = ""
        self.calibrator: Optional[TemperatureScalingCalibrator] = None
        self.features_used: List[str] = []
        self.metrics: Optional[MoneylineEngineMetrics] = None
        self.is_fitted: bool = False

    def fit(
        self,
        train_df: pd.DataFrame,
        features: List[str],
        target_col: str = 'home_team_won',
        test_df: Optional[pd.DataFrame] = None,
    ) -> MoneylineEngineMetrics:
        """
        Entraîne l'ensemble XGB+LGB et calibre via Temperature Scaling.

        Args:
            train_df    : DataFrame déjà feature-engineered (chronologique)
            features    : Liste des colonnes features
            target_col  : Colonne cible binaire (défaut: 'home_team_won')
            test_df     : DataFrame de test (optionnel, pour métriques out-of-sample)
        """
        import xgboost as xgb
        try:
            import lightgbm as lgb
        except ImportError:
            raise ImportError(
                "lightgbm n'est pas installé. Installer avec : pip install lightgbm\n"
                "Ou désactiver l'ensemble dans config.yaml (XGB seul)."
            )

        if self.verbose:
            print("📊 Entraînement NHLMoneylineEngine (XGB + LGB ensemble)")
            print("=" * 60)

        # Tri chronologique + split val
        train_df = train_df.sort_values('gameDate_home').reset_index(drop=True)
        n = len(train_df)
        n_val = int(n * self.val_fraction)
        train_inner = train_df.iloc[:-n_val] if n_val > 0 else train_df
        val_inner = train_df.iloc[-n_val:] if n_val > 0 else train_df.iloc[-100:]

        X_tr_raw = train_inner.reindex(columns=features, fill_value=0)
        y_tr = train_inner[target_col].astype(int)
        X_val_raw = val_inner.reindex(columns=features, fill_value=0)
        y_val = val_inner[target_col].astype(int)

        # Scaling (StandardScaler comme dans le notebook)
        self.scaler = StandardScaler()
        X_tr = pd.DataFrame(
            self.scaler.fit_transform(X_tr_raw),
            columns=features, index=X_tr_raw.index,
        )
        X_val = pd.DataFrame(
            self.scaler.transform(X_val_raw),
            columns=features, index=X_val_raw.index,
        )

        if self.verbose:
            print(f"Train interne : {len(X_tr):,}  |  Val : {len(X_val):,}  "
                  f"|  Features : {len(features)}")

        # XGBoost
        if self.verbose:
            print("🔧 XGBoost...")
        self.xgb_model = xgb.XGBClassifier(
            **self.xgb_params,
            early_stopping_rounds=30,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.xgb_model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)

        # LightGBM
        if self.verbose:
            print("🔧 LightGBM...")
        self.lgb_model = lgb.LGBMClassifier(**self.lgb_params)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.lgb_model.fit(
                X_tr, y_tr,
                eval_set=[(X_val, y_val)],
                callbacks=[lgb.early_stopping(30, verbose=False),
                           lgb.log_evaluation(-1)],
            )

        # Métriques val
        p_xgb_val = self.xgb_model.predict_proba(X_val)[:, 1]
        p_lgb_val = self.lgb_model.predict_proba(X_val)[:, 1]
        auc_xgb_val = roc_auc_score(y_val, p_xgb_val)
        auc_lgb_val = roc_auc_score(y_val, p_lgb_val)

        # Choix du meilleur modèle (utilisé comme primary pour calibration)
        if auc_lgb_val >= auc_xgb_val:
            self.best_name = 'LGB'
            best_val_raw = p_lgb_val
        else:
            self.best_name = 'XGB'
            best_val_raw = p_xgb_val

        if self.verbose:
            print(f"  AUC val XGB : {auc_xgb_val:.4f}")
            print(f"  AUC val LGB : {auc_lgb_val:.4f}")
            print(f"  Best model  : {self.best_name}")

        # Calibration Temperature Scaling sur val (raw du best model)
        if self.verbose:
            print("🌡️  Calibration Temperature Scaling...")
        self.calibrator = TemperatureScalingCalibrator().fit(best_val_raw, y_val.values)
        if self.verbose:
            t_msg = "sur-confiant" if self.calibrator.T < 1 else "sous-confiant"
            print(f"  T optimal : {self.calibrator.T:.3f} ({t_msg})")

        self.features_used = features
        self.is_fitted = True

        # Métriques test
        if test_df is not None and len(test_df) > 0:
            X_test_raw = test_df.reindex(columns=features, fill_value=0)
            X_test = pd.DataFrame(
                self.scaler.transform(X_test_raw),
                columns=features, index=X_test_raw.index,
            )
            y_test = test_df[target_col].astype(int)
            p_raw = self._predict_raw(X_test)
            p_cal = self.calibrator.predict(p_raw)
            auc_test = roc_auc_score(y_test, p_cal)
            acc_test = accuracy_score(y_test, (p_cal > 0.5).astype(int))
            brier_raw = brier_score_loss(y_test, p_raw)
            brier_cal = brier_score_loss(y_test, p_cal)
            n_test = len(test_df)
            if self.verbose:
                print(f"📈 Test (n={n_test:,}) :")
                print(f"   AUC test            : {auc_test:.4f}")
                print(f"   Accuracy test       : {acc_test:.4f}")
                print(f"   Brier raw test      : {brier_raw:.4f}")
                print(f"   Brier calibré test  : {brier_cal:.4f}")
        else:
            auc_test = acc_test = brier_raw = brier_cal = 0.0
            n_test = 0

        self.metrics = MoneylineEngineMetrics(
            n_train=len(X_tr), n_val=len(X_val), n_test=n_test,
            auc_xgb_val=float(auc_xgb_val), auc_lgb_val=float(auc_lgb_val),
            best_model_name=self.best_name,
            auc_test=float(auc_test), accuracy_test=float(acc_test),
            brier_raw_test=float(brier_raw), brier_calibrated_test=float(brier_cal),
            temperature=float(self.calibrator.T),
            features_used=features,
        )
        return self.metrics

    def _predict_raw(self, X_scaled: pd.DataFrame) -> np.ndarray:
        """Proba brute via le meilleur modèle (avant calibration)."""
        if self.best_name == 'LGB':
            return self.lgb_model.predict_proba(X_scaled)[:, 1]
        return self.xgb_model.predict_proba(X_scaled)[:, 1]

    def predict_proba_home_wins(self, X: pd.DataFrame) -> np.ndarray:
        """
        Proba calibrée P(home_wins) pour des features non-scaled.
        Applique automatiquement le scaler interne.
        """
        if not self.is_fitted:
            raise RuntimeError("NHLMoneylineEngine non entraîné. Appeler fit() d'abord.")
        X_aligned = X.reindex(columns=self.features_used, fill_value=0)
        X_scaled = pd.DataFrame(
            self.scaler.transform(X_aligned),
            columns=self.features_used, index=X_aligned.index,
        )
        raw = self._predict_raw(X_scaled)
        return self.calibrator.predict(raw)
