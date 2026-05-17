"""
Classe de base pour tous les modèles NBA.

Ce module définit la classe abstraite BaseNBAModel qui sert de base
pour tous les modèles de prédiction NBA (victoires, totaux, spreads, props).
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import pandas as pd


class BaseNBAModel(ABC):
    """
    Classe de base abstraite pour tous les modèles NBA.
    
    Cette classe définit l'interface commune que tous les modèles NBA
    doivent implémenter. Elle gère également l'état du modèle pour
    la sauvegarde et le chargement.
    
    Attributes:
        model: Le modèle ML sous-jacent (XGBoost, LightGBM, etc.)
        feature_columns: Liste des colonnes de features utilisées par le modèle
        is_trained: Indique si le modèle a été entraîné
        metrics: Dictionnaire contenant les métriques de performance
    """
    
    def __init__(self):
        """Initialise un nouveau modèle NBA."""
        self.model: Optional[Any] = None
        self.feature_columns: Optional[List[str]] = None
        self.is_trained: bool = False
        self.metrics: Dict[str, float] = {}
    
    @abstractmethod
    def prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Prépare les features spécifiques au modèle.
        
        Cette méthode doit être implémentée par chaque modèle pour
        sélectionner et transformer les features appropriées.
        
        Args:
            df: DataFrame contenant les données brutes
            
        Returns:
            DataFrame avec les features préparées
        """
        pass
    
    @abstractmethod
    def train(self, train_df: pd.DataFrame, test_df: pd.DataFrame) -> Dict[str, float]:
        """
        Entraîne le modèle sur les données d'entraînement.
        
        Cette méthode doit être implémentée par chaque modèle pour
        définir la logique d'entraînement spécifique.
        
        Args:
            train_df: DataFrame contenant les données d'entraînement
            test_df: DataFrame contenant les données de test
            
        Returns:
            Dictionnaire contenant les métriques de performance
        """
        pass
    
    @abstractmethod
    def predict(self, df: pd.DataFrame) -> Any:
        """
        Fait des prédictions sur de nouvelles données.
        
        Cette méthode doit être implémentée par chaque modèle pour
        définir la logique de prédiction spécifique.
        
        Args:
            df: DataFrame contenant les données pour la prédiction
            
        Returns:
            Prédictions (le type dépend du modèle)
        """
        pass
    
    def get_state(self) -> Dict[str, Any]:
        """
        Retourne l'état du modèle pour la sauvegarde.
        
        Cette méthode permet de sérialiser l'état complet du modèle
        pour le sauvegarder dans un fichier pickle.
        
        Returns:
            Dictionnaire contenant l'état du modèle avec les clés:
            - model: Le modèle ML entraîné
            - feature_columns: Liste des colonnes de features
            - is_trained: Statut d'entraînement
            - metrics: Métriques de performance
        """
        return {
            'model': self.model,
            'feature_columns': self.feature_columns,
            'is_trained': self.is_trained,
            'metrics': self.metrics
        }
    
    def set_state(self, state: Dict[str, Any]) -> None:
        """
        Restaure l'état du modèle depuis un dictionnaire.
        
        Cette méthode permet de désérialiser l'état du modèle
        après chargement depuis un fichier pickle.
        
        Args:
            state: Dictionnaire contenant l'état du modèle
        """
        self.model = state['model']
        self.feature_columns = state['feature_columns']
        self.is_trained = state['is_trained']
        self.metrics = state.get('metrics', {})
