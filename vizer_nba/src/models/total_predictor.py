"""
Modèle de prédiction de totaux de points (Under/Over) pour matchs NBA
"""
import pandas as pd
import numpy as np
from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from typing import Tuple, Dict

from src.models.base import BaseNBAModel


class NBATotalPredictor(BaseNBAModel):
    """Prédicteur de totaux de points pour matchs NBA"""
    
    def __init__(self, hyperparameters: dict = None):
        """
        Initialise le modèle.

        Args:
            hyperparameters : Dict d'hyperparamètres XGBoost. Lu depuis config.yaml.
                              Si None, utilise les valeurs par défaut.

        Clés spéciales gérées hors de XGBoost lui-même :
            - early_stopping_rounds : si défini, active l'early stopping avec un
              split chronologique 85/15 du train set comme validation interne.
            - val_fraction : fraction du train à réserver pour l'early stopping
              (défaut 0.15). Le split est chronologique (les derniers matchs).
        """
        super().__init__()
        self.hyperparameters = hyperparameters or {}

        defaults = {
            'n_estimators': 200,
            'max_depth': 6,
            'learning_rate': 0.1,
            'random_state': 42,
        }
        params = {**defaults, **self.hyperparameters}
        params.pop('model', None)

        # Hyperparams qui ne sont PAS passés à XGBRegressor (gérés dans train)
        self._early_stopping_rounds = params.pop('early_stopping_rounds', None)
        self._val_fraction = params.pop('val_fraction', 0.15)

        self.model = XGBRegressor(**params)
    
    def prepare_features(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
        """
        Prépare les features et la target pour l'entraînement
        
        Args:
            df: DataFrame avec toutes les features
            
        Returns:
            (X, y) - Features et target (total de points)
        """
        # Colonnes à exclure
        exclude_cols = [
            'GAME_ID', 'GAME_DATE', 'SEASON_ID',
            'HOME_TEAM_ID', 'HOME_TEAM_ABBREVIATION',
            'AWAY_TEAM_ID', 'AWAY_TEAM_ABBREVIATION',
            'HOME_WL', 'HOME_WIN',
            'HOME_PTS', 'AWAY_PTS', 'TOTAL_PTS',  # Target
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
        y = df['TOTAL_PTS'].copy()
        
        # Sauvegarder les colonnes
        self.feature_columns = feature_cols
        
        return X, y
    
    def train(
        self, 
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
        verbose: bool = True
    ) -> Dict:
        """
        Entraîne le modèle avec validation temporelle
        
        Args:
            train_df: DataFrame avec features et target pour l'entraînement
            test_df: DataFrame avec features et target pour le test
            verbose: Afficher les résultats
            
        Returns:
            Dictionnaire avec les métriques de performance
        """
        # Préparer les features
        X_train, y_train = self.prepare_features(train_df)
        X_test, y_test = self.prepare_features(test_df)
        
        if verbose:
            print("📊 Entraînement du modèle de totaux")
            print("=" * 50)
            print(f"Train: {len(X_train):,} matchs")
            print(f"Test:  {len(X_test):,} matchs")
            print(f"Features: {len(self.feature_columns)}")
        
        # Entraîner — avec early stopping si configuré
        if self._early_stopping_rounds:
            # Split chronologique : 85% train interne / 15% val
            # (train_df est trié par GAME_DATE par prepare_match_data)
            n_split = int(len(X_train) * (1 - self._val_fraction))
            X_tr, X_val = X_train.iloc[:n_split], X_train.iloc[n_split:]
            y_tr, y_val = y_train.iloc[:n_split], y_train.iloc[n_split:]

            if verbose:
                print(f"⏱️  Early stopping activé : {len(X_tr):,} train interne / {len(X_val):,} val")
                print(f"   Patience : {self._early_stopping_rounds} rounds")

            self.model.set_params(early_stopping_rounds=self._early_stopping_rounds)
            self.model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)

            if verbose:
                try:
                    print(f"   Best iteration: {self.model.best_iteration} / {self.model.n_estimators}")
                except AttributeError:
                    pass
        else:
            self.model.fit(X_train, y_train)
        self.is_trained = True
        
        # Prédictions
        y_pred_train = self.model.predict(X_train)
        y_pred_test = self.model.predict(X_test)
        
        # Métriques
        train_mae = mean_absolute_error(y_train, y_pred_train)
        test_mae = mean_absolute_error(y_test, y_pred_test)
        train_rmse = np.sqrt(mean_squared_error(y_train, y_pred_train))
        test_rmse = np.sqrt(mean_squared_error(y_test, y_pred_test))
        train_r2 = r2_score(y_train, y_pred_train)
        test_r2 = r2_score(y_test, y_pred_test)
        
        # Sauvegarder les métriques
        self.metrics = {
            'train_mae': train_mae,
            'test_mae': test_mae,
            'train_rmse': train_rmse,
            'test_rmse': test_rmse,
            'train_r2': train_r2,
            'test_r2': test_r2,
            'n_train': len(X_train),
            'n_test': len(X_test)
        }
        
        if verbose:
            print(f"\n✅ Entraînement terminé")
            print(f"MAE train:  {train_mae:.2f} points")
            print(f"MAE test:   {test_mae:.2f} points")
            print(f"RMSE train: {train_rmse:.2f} points")
            print(f"RMSE test:  {test_rmse:.2f} points")
            print(f"R² train:   {train_r2:.3f}")
            print(f"R² test:    {test_r2:.3f}")
            
            # Statistiques sur les erreurs
            errors = np.abs(y_test - y_pred_test)
            print(f"\n📈 Distribution des erreurs (test):")
            print(f"  Médiane: {np.median(errors):.2f} points")
            print(f"  90e percentile: {np.percentile(errors, 90):.2f} points")
        
        # Feature importance
        feature_importance = pd.DataFrame({
            'feature': self.feature_columns,
            'importance': self.model.feature_importances_
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
        Prédit le total de points
        
        Args:
            df: DataFrame avec les features
            
        Returns:
            Array de prédictions (total de points)
        """
        if not self.is_trained:
            raise ValueError("Le modèle n'est pas entraîné. Appelez train() d'abord.")
        
        X = df[self.feature_columns]
        return self.model.predict(X)
    
    def predict_under_over(
        self, 
        df: pd.DataFrame, 
        line: float
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Prédit under/over par rapport à une ligne
        
        Args:
            df: DataFrame avec les features
            line: Ligne de total (ex: 220.5)
            
        Returns:
            (predictions, probabilities) - Prédictions de total et probabilité d'over
        """
        predictions = self.predict(df)
        
        # Calculer la probabilité d'over basée sur l'écart à la ligne
        # Plus la prédiction est au-dessus de la ligne, plus la probabilité est élevée
        diff = predictions - line
        
        # Utiliser une fonction sigmoïde pour convertir en probabilité
        # Ajuster le facteur pour calibrer (ici 15 = ~15 points = ~73% de confiance)
        # Plus ce nombre est élevé, plus le modèle est prudent
        probabilities = 1 / (1 + np.exp(-diff / 15))
        
        return predictions, probabilities
