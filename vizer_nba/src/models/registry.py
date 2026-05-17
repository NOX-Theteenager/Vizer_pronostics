"""
Registre unifié pour tous les modèles NBA.

Ce module définit la classe ModelRegistry qui gère l'enregistrement,
la sauvegarde et le chargement de tous les modèles NBA dans un seul fichier.
"""

import pickle
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path


class ModelRegistry:
    """
    Registre unifié pour gérer tous les modèles NBA.
    
    Cette classe permet d'enregistrer plusieurs modèles (victoires, totaux, etc.)
    dans une structure organisée avec leurs métadonnées et métriques de performance.
    Tous les modèles sont sauvegardés dans un seul fichier pickle.
    
    Attributes:
        version: Version du registre (format semver)
        created_at: Timestamp de création du registre
        models: Dictionnaire contenant tous les modèles enregistrés
        metadata: Métadonnées globales sur l'entraînement
    """
    
    VERSION = '1.0.0'
    
    def __init__(self):
        """Initialise un nouveau registre de modèles."""
        self.version: str = self.VERSION
        self.created_at: str = datetime.now().isoformat()
        self.models: Dict[str, Dict[str, Any]] = {}
        self.metadata: Dict[str, Any] = {}
    
    def register(
        self,
        model_name: str,
        model: Any,
        metrics: Dict[str, float],
        feature_columns: Optional[list] = None,
        hyperparameters: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Enregistre un modèle avec ses métadonnées.
        
        Args:
            model_name: Nom unique du modèle (ex: 'win', 'total')
            model: Instance du modèle (doit avoir une méthode get_state())
            metrics: Dictionnaire des métriques de performance
            feature_columns: Liste des colonnes de features (optionnel)
            hyperparameters: Hyperparamètres du modèle (optionnel)
        
        Raises:
            ValueError: Si le modèle n'a pas de méthode get_state()
        """
        # Vérifier que le modèle a une méthode get_state
        if not hasattr(model, 'get_state'):
            raise ValueError(
                f"Le modèle '{model_name}' doit avoir une méthode get_state()"
            )
        
        # Récupérer l'état du modèle
        model_state = model.get_state()
        
        # Utiliser les feature_columns du modèle si non fournis
        if feature_columns is None:
            feature_columns = model_state.get('feature_columns', [])
        
        # Enregistrer le modèle avec toutes ses métadonnées
        self.models[model_name] = {
            'model': model_state['model'],
            'feature_columns': feature_columns,
            'metrics': metrics,
            'hyperparameters': hyperparameters or {},
            'is_trained': model_state.get('is_trained', True)
        }
    
    def get_model(self, model_name: str) -> Dict[str, Any]:
        """
        Récupère un modèle enregistré.
        
        Args:
            model_name: Nom du modèle à récupérer
            
        Returns:
            Dictionnaire contenant le modèle et ses métadonnées
            
        Raises:
            KeyError: Si le modèle n'existe pas dans le registre
        """
        if model_name not in self.models:
            available = ', '.join(self.models.keys())
            raise KeyError(
                f"Modèle '{model_name}' non trouvé. "
                f"Modèles disponibles: {available}"
            )
        
        return self.models[model_name]
    
    def save(self, filepath: str) -> None:
        """
        Sauvegarde le registre complet dans un fichier pickle.
        
        Args:
            filepath: Chemin du fichier de sauvegarde
        """
        # Créer le dossier parent si nécessaire
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        
        # Préparer les données à sauvegarder
        data = {
            'version': self.version,
            'created_at': self.created_at,
            'models': self.models,
            'metadata': self.metadata
        }
        
        # Sauvegarder avec pickle
        with open(filepath, 'wb') as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
    
    @classmethod
    def load(cls, filepath: str) -> 'ModelRegistry':
        """
        Charge un registre depuis un fichier pickle.
        
        Args:
            filepath: Chemin du fichier à charger
            
        Returns:
            Instance de ModelRegistry chargée depuis le fichier
            
        Raises:
            FileNotFoundError: Si le fichier n'existe pas
            ValueError: Si la version du registre est incompatible
        """
        # Vérifier que le fichier existe
        if not Path(filepath).exists():
            raise FileNotFoundError(f"Fichier non trouvé: {filepath}")
        
        # Charger les données
        with open(filepath, 'rb') as f:
            data = pickle.load(f)
        
        # Vérifier la version (pour compatibilité future)
        loaded_version = data.get('version', '0.0.0')
        if loaded_version.split('.')[0] != cls.VERSION.split('.')[0]:
            raise ValueError(
                f"Version incompatible: {loaded_version} "
                f"(attendue: {cls.VERSION})"
            )
        
        # Créer une nouvelle instance et restaurer l'état
        registry = cls()
        registry.version = data['version']
        registry.created_at = data['created_at']
        registry.models = data['models']
        registry.metadata = data.get('metadata', {})
        
        return registry
    
    def print_summary(self) -> None:
        """
        Affiche un résumé de tous les modèles enregistrés.
        
        Affiche les informations suivantes:
        - Version du registre
        - Date de création
        - Liste des modèles avec leurs métriques
        - Métadonnées globales
        """
        print("=" * 70)
        print("RÉSUMÉ DU REGISTRE DE MODÈLES NBA")
        print("=" * 70)
        print(f"Version: {self.version}")
        print(f"Créé le: {self.created_at}")
        print(f"Nombre de modèles: {len(self.models)}")
        print()
        
        # Afficher chaque modèle
        for model_name, model_data in self.models.items():
            print(f"Modèle: {model_name.upper()}")
            print("-" * 70)
            
            # Features
            n_features = len(model_data.get('feature_columns', []))
            print(f"  Nombre de features: {n_features}")
            
            # Métriques
            metrics = model_data.get('metrics', {})
            if metrics:
                print("  Métriques:")
                for metric_name, metric_value in metrics.items():
                    # Vérifier si c'est un nombre avant de formater
                    if isinstance(metric_value, (int, float)):
                        print(f"    - {metric_name}: {metric_value:.4f}")
                    else:
                        print(f"    - {metric_name}: {metric_value}")
            
            # Hyperparamètres
            hyperparams = model_data.get('hyperparameters', {})
            if hyperparams:
                print("  Hyperparamètres:")
                for param_name, param_value in hyperparams.items():
                    print(f"    - {param_name}: {param_value}")
            
            print()
        
        # Métadonnées globales
        if self.metadata:
            print("MÉTADONNÉES GLOBALES")
            print("-" * 70)
            for key, value in self.metadata.items():
                print(f"  {key}: {value}")
            print()
        
        print("=" * 70)
    
    def set_metadata(self, key: str, value: Any) -> None:
        """
        Définit une métadonnée globale.
        
        Args:
            key: Clé de la métadonnée
            value: Valeur de la métadonnée
        """
        self.metadata[key] = value
    
    def get_metadata(self, key: str, default: Any = None) -> Any:
        """
        Récupère une métadonnée globale.
        
        Args:
            key: Clé de la métadonnée
            default: Valeur par défaut si la clé n'existe pas
            
        Returns:
            Valeur de la métadonnée ou la valeur par défaut
        """
        return self.metadata.get(key, default)
    
    def list_models(self) -> list:
        """
        Retourne la liste des noms de modèles enregistrés.
        
        Returns:
            Liste des noms de modèles
        """
        return list(self.models.keys())
    
    def __repr__(self) -> str:
        """Représentation string du registre."""
        return (
            f"ModelRegistry(version={self.version}, "
            f"models={list(self.models.keys())}, "
            f"created_at={self.created_at})"
        )
