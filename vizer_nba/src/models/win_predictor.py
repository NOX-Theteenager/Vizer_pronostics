"""
Modèle de prédiction de résultats de matchs NBA
"""
import pandas as pd
import numpy as np
from xgboost import XGBClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, brier_score_loss
from sklearn.calibration import CalibratedClassifierCV
from typing import Tuple, Dict

from src.models.base import BaseNBAModel


class NBAMatchPredictor(BaseNBAModel):
    """Prédicteur de résultats de matchs NBA"""
    
    def __init__(self, calibrate: bool = True, hyperparameters: dict = None):
        """
        Initialise le modèle.

        Args:
            calibrate       : Si True, calibre les probabilités pour réduire la sur-confiance.
            hyperparameters : Dict d'hyperparamètres XGBoost. Lu depuis config.yaml en pratique.
                              Si None, utilise les valeurs par défaut.
        """
        super().__init__()
        self.calibrate = calibrate
        self.hyperparameters = hyperparameters or {}

        # Valeurs par défaut, écrasées par hyperparameters si fournis.
        defaults = {
            'n_estimators': 200,
            'max_depth': 6,
            'learning_rate': 0.1,
            'random_state': 42,
            'eval_metric': 'logloss',
        }
        params = {**defaults, **self.hyperparameters}
        # Retirer le champ 'model' si présent (vient de config: model: xgboost)
        params.pop('model', None)

        self.base_model = XGBClassifier(**params)
        self.model = None  # Sera le modèle calibré ou base_model
    
    def prepare_features(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
        """
        Prépare les features et la target pour l'entraînement
        
        Args:
            df: DataFrame avec toutes les features
            
        Returns:
            (X, y) - Features et target
        """
        # Colonnes à exclure
        exclude_cols = [
            'GAME_ID', 'GAME_DATE', 'SEASON_ID',
            'HOME_TEAM_ID', 'HOME_TEAM_ABBREVIATION',
            'AWAY_TEAM_ID', 'AWAY_TEAM_ABBREVIATION',
            'HOME_WL', 'HOME_WIN',  # Target
            'HOME_PTS', 'AWAY_PTS', 'TOTAL_PTS',  # Scores du match courant (inconnus avant le match)
            # Leakage: Stats du match en cours (ne sont pas connues avant le match)
            'HOME_FG_PCT', 'AWAY_FG_PCT',
            'HOME_FG3_PCT', 'AWAY_FG3_PCT',
            'HOME_FT_PCT', 'AWAY_FT_PCT',
            'HOME_REB', 'AWAY_REB',
            'HOME_AST', 'AWAY_AST',
            'HOME_STL', 'AWAY_STL',
            'HOME_BLK', 'AWAY_BLK',
            'HOME_TOV', 'AWAY_TOV',
            # Nouvelles métriques (Data Leakage)
            'HOME_EFG_PCT', 'AWAY_EFG_PCT',
            'HOME_TOV_PCT', 'AWAY_TOV_PCT',
            'HOME_FT_RATE', 'AWAY_FT_RATE',
            'HOME_POSS', 'AWAY_POSS',
            'HOME_OFF_RATING', 'AWAY_OFF_RATING',
            'HOME_DEF_RATING', 'AWAY_DEF_RATING',
        ]
        
        # Sélectionner les features
        feature_cols = [col for col in df.columns if col not in exclude_cols]
        
        X = df[feature_cols].copy()
        y = df['HOME_WIN'].copy()
        
        # Sauvegarder les colonnes pour la prédiction
        self.feature_columns = feature_cols
        
        return X, y
    
    def train(
        self,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
        verbose: bool = True,
    ) -> Dict:
        """
        Entraîne le modèle avec validation temporelle.

        Si calibrate=True, applique une calibration isotonique sur un split
        chronologique de la fin du train (calib_fraction, défaut 15 %).
        On utilise cv='prefit' (et non cv=5) pour respecter l'ordre temporel :
        les folds aléatoires de cv=5 mélangeraient passé et futur sur des données
        de séries temporelles.
        """
        calib_fraction = self.hyperparameters.get('calib_fraction', 0.15)

        X_train_full, y_train_full = self.prepare_features(train_df)
        X_test, y_test = self.prepare_features(test_df)

        if verbose:
            print("📊 Entraînement du modèle")
            print("=" * 50)
            print(f"Train: {len(X_train_full):,} matchs")
            print(f"Test:  {len(X_test):,} matchs")
            print(f"Features: {len(self.feature_columns)}")
            if self.calibrate:
                n_calib = int(len(X_train_full) * calib_fraction)
                print(f"⚙️  Calibration isotonique — split chrono "
                      f"{100*(1-calib_fraction):.0f}%/{100*calib_fraction:.0f}% "
                      f"({len(X_train_full)-n_calib:,} fit / {n_calib:,} calib)")

        if self.calibrate:
            # Split chronologique : les matchs les plus récents servent à calibrer
            calib_idx = int(len(X_train_full) * (1 - calib_fraction))
            X_fit,   y_fit   = X_train_full.iloc[:calib_idx],  y_train_full.iloc[:calib_idx]
            X_calib, y_calib = X_train_full.iloc[calib_idx:],  y_train_full.iloc[calib_idx:]

            # 1. XGBoost entraîné sur les matchs les plus anciens
            self.base_model.fit(X_fit, y_fit)

            # 2. Calibration isotonique sur les matchs les plus récents (cv='prefit')
            if verbose:
                print("🔧 Calibration isotonique (cv='prefit', split chrono)...")
            self.model = CalibratedClassifierCV(
                self.base_model,
                method='isotonic',
                cv='prefit',
            )
            self.model.fit(X_calib, y_calib)

            # Brier avant / après calibration sur le set de calibration
            if verbose:
                raw_proba  = self.base_model.predict_proba(X_calib)[:, 1]
                cal_proba  = self.model.predict_proba(X_calib)[:, 1]
                brier_raw  = brier_score_loss(y_calib, raw_proba)
                brier_cal  = brier_score_loss(y_calib, cal_proba)
                delta      = brier_raw - brier_cal
                sign       = "↓" if delta > 0 else "↑"
                print(f"   Brier (calib set) : {brier_raw:.4f} → {brier_cal:.4f} "
                      f"({sign}{abs(delta):.4f})")
        else:
            self.base_model.fit(X_train_full, y_train_full)
            self.model = self.base_model

        self.is_trained = True

        # Prédictions
        y_pred_train = self.model.predict(X_train_full)
        y_pred_test  = self.model.predict(X_test)

        # Probabilités
        y_proba_train = self.model.predict_proba(X_train_full)[:, 1]
        y_proba_test  = self.model.predict_proba(X_test)[:, 1]
        
        # Métriques
        train_acc = accuracy_score(y_train_full, y_pred_train)
        test_acc  = accuracy_score(y_test,       y_pred_test)

        # Brier score (mesure de calibration)
        train_brier = brier_score_loss(y_train_full, y_proba_train)
        test_brier  = brier_score_loss(y_test,       y_proba_test)

        # Sauvegarder les métriques
        self.metrics = {
            'train_accuracy':   train_acc,
            'test_accuracy':    test_acc,
            'train_brier_score': train_brier,
            'test_brier_score':  test_brier,
            'n_train': len(X_train_full),
            'n_test':  len(X_test),
            'calibrated': self.calibrate,
            'calibration_method': 'isotonic_prefit_chrono' if self.calibrate else 'none',
        }
        
        if verbose:
            print(f"\n✅ Entraînement terminé")
            print(f"Précision train: {train_acc:.1%}")
            print(f"Précision test:  {test_acc:.1%}")
            print(f"Brier score train: {train_brier:.4f} (plus bas = mieux calibré)")
            print(f"Brier score test:  {test_brier:.4f}")
            
            print(f"\n📈 Rapport de classification (Test):")
            print(classification_report(
                y_test, y_pred_test,
                target_names=['Away Win', 'Home Win']
            ))
            
            print(f"Matrice de confusion:")
            cm = confusion_matrix(y_test, y_pred_test)
            print(f"  Away Win prédit: {cm[0]}")
            print(f"  Home Win prédit: {cm[1]}")
            
            # Analyser la distribution des probabilités
            print(f"\n📊 Distribution des probabilités (Test):")
            proba_bins = [0, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
            proba_counts = pd.cut(y_proba_test, bins=proba_bins).value_counts().sort_index()
            for bin_range, count in proba_counts.items():
                pct = count / len(y_proba_test) * 100
                print(f"  {bin_range}: {count:4d} ({pct:5.1f}%)")
        
        # Feature importance (du modèle de base)
        if self.calibrate:
            # Pour un modèle calibré, récupérer les importances du premier estimateur
            feature_importance = pd.DataFrame({
                'feature': self.feature_columns,
                'importance': self.model.calibrated_classifiers_[0].estimator.feature_importances_
            }).sort_values('importance', ascending=False)
        else:
            feature_importance = pd.DataFrame({
                'feature': self.feature_columns,
                'importance': self.base_model.feature_importances_
            }).sort_values('importance', ascending=False)
        
        if verbose:
            print(f"\n🔝 Top 10 features importantes:")
            for idx, row in feature_importance.head(10).iterrows():
                print(f"  {row['feature']}: {row['importance']:.4f}")
        
        # Ajouter feature importance aux métriques
        self.metrics['feature_importance'] = feature_importance
        
        return self.metrics
    
    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """
        Prédit le résultat de matchs
        
        Args:
            df: DataFrame avec les features
            
        Returns:
            Array de prédictions (1 = home win, 0 = away win)
        """
        if not self.is_trained:
            raise ValueError("Le modèle n'est pas entraîné. Appelez train() d'abord.")
        
        X = df[self.feature_columns]
        return self.model.predict(X)
    
    def predict_proba(self, df: pd.DataFrame) -> np.ndarray:
        """
        Prédit les probabilités de victoire
        
        Args:
            df: DataFrame avec les features
            
        Returns:
            Array de probabilités [proba_away_win, proba_home_win]
        """
        if not self.is_trained:
            raise ValueError("Le modèle n'est pas entraîné. Appelez train() d'abord.")
        
        X = df[self.feature_columns]
        return self.model.predict_proba(X)


if __name__ == "__main__":
    from src.data.loader import NBADataLoader
    from src.features.engineer import MatchFeatureEngineer
    
    print("🏀 NBA Match Predictor - Entraînement")
    print("=" * 70)
    print()
    
    # 1. Charger les données
    print("📂 Chargement des données...")
    loader = NBADataLoader()
    games = loader.load_games()
    print(f"  ✓ {len(games):,} matchs chargés")
    
    # 2. Prendre les saisons récentes pour l'entraînement
    # IMPORTANT: Utiliser uniquement les saisons COMPLÈTES pour éviter le data leakage
    # Saison 2024-25 se termine en avril 2025, donc on prend jusqu'à 2024-25
    recent_games = games[
        (games['SEASON_ID'] >= 22020) & 
        (games['SEASON_ID'] <= 22024)  # Jusqu'à la saison 2024-25 (complète)
    ].copy()
    print(f"  ✓ {len(recent_games):,} matchs récents (2020-2025, saisons complètes)")
    print()
    
    # 3. Créer les features
    print("🔧 Feature Engineering...")
    engineer = MatchFeatureEngineer(windows=[5, 10, 20])
    features_df = engineer.create_features(recent_games, include_h2h=False)
    print()
    
    # 4. Split temporel
    split_idx = int(len(features_df) * 0.8)
    train_df = features_df[:split_idx]
    test_df = features_df[split_idx:]
    
    # 5. Entraîner le modèle
    predictor = NBAMatchPredictor()
    metrics = predictor.train(train_df, test_df, verbose=True)
    print()
    
    print("=" * 70)
    print("✅ ENTRAÎNEMENT TERMINÉ")
    print("=" * 70)
