"""
Tests unitaires pour le ModelRegistry.

Ce module teste toutes les fonctionnalités du registre de modèles:
- Enregistrement de modèles
- Récupération de modèles
- Sauvegarde et chargement
- Gestion des métadonnées
"""

import pytest
import tempfile
import os
from pathlib import Path
from src.models.registry import ModelRegistry
from src.models.base import BaseNBAModel
import pandas as pd


class MockModel(BaseNBAModel):
    """Modèle mock pour les tests."""
    
    def __init__(self, name: str = "mock"):
        super().__init__()
        self.name = name
        self.model = f"mock_model_{name}"
        self.feature_columns = ['feature1', 'feature2', 'feature3']
        self.is_trained = True
        self.metrics = {'accuracy': 0.85, 'mae': 10.5}
    
    def prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        return df
    
    def train(self, train_df: pd.DataFrame, test_df: pd.DataFrame):
        return self.metrics
    
    def predict(self, df: pd.DataFrame):
        return [1, 0, 1]


class TestModelRegistry:
    """Tests pour la classe ModelRegistry."""
    
    def test_init(self):
        """Test l'initialisation du registre."""
        registry = ModelRegistry()
        
        assert registry.version == ModelRegistry.VERSION
        assert registry.created_at is not None
        assert isinstance(registry.models, dict)
        assert len(registry.models) == 0
        assert isinstance(registry.metadata, dict)
    
    def test_register_model(self):
        """Test l'enregistrement d'un modèle."""
        registry = ModelRegistry()
        model = MockModel("test")
        metrics = {'accuracy': 0.85, 'mae': 10.5}
        
        registry.register('test_model', model, metrics)
        
        assert 'test_model' in registry.models
        assert registry.models['test_model']['metrics'] == metrics
        assert len(registry.models['test_model']['feature_columns']) == 3
    
    def test_register_multiple_models(self):
        """Test l'enregistrement de plusieurs modèles."""
        registry = ModelRegistry()
        
        model1 = MockModel("win")
        model2 = MockModel("total")
        
        registry.register('win', model1, {'accuracy': 0.85})
        registry.register('total', model2, {'mae': 10.5})
        
        assert len(registry.models) == 2
        assert 'win' in registry.models
        assert 'total' in registry.models
    
    def test_register_with_hyperparameters(self):
        """Test l'enregistrement avec hyperparamètres."""
        registry = ModelRegistry()
        model = MockModel("test")
        metrics = {'accuracy': 0.85}
        hyperparams = {'learning_rate': 0.1, 'max_depth': 5}
        
        registry.register('test', model, metrics, hyperparameters=hyperparams)
        
        assert registry.models['test']['hyperparameters'] == hyperparams
    
    def test_register_invalid_model(self):
        """Test l'enregistrement d'un modèle invalide."""
        registry = ModelRegistry()
        invalid_model = "not a model"
        
        with pytest.raises(ValueError, match="doit avoir une méthode get_state"):
            registry.register('invalid', invalid_model, {})
    
    def test_get_model(self):
        """Test la récupération d'un modèle."""
        registry = ModelRegistry()
        model = MockModel("test")
        metrics = {'accuracy': 0.85}
        
        registry.register('test', model, metrics)
        retrieved = registry.get_model('test')
        
        assert retrieved is not None
        assert retrieved['metrics'] == metrics
        assert 'model' in retrieved
        assert 'feature_columns' in retrieved
    
    def test_get_nonexistent_model(self):
        """Test la récupération d'un modèle inexistant."""
        registry = ModelRegistry()
        
        with pytest.raises(KeyError, match="non trouvé"):
            registry.get_model('nonexistent')
    
    def test_save_and_load(self):
        """Test la sauvegarde et le chargement du registre."""
        # Créer un registre avec des modèles
        registry1 = ModelRegistry()
        model1 = MockModel("win")
        model2 = MockModel("total")
        
        registry1.register('win', model1, {'accuracy': 0.85})
        registry1.register('total', model2, {'mae': 10.5})
        registry1.set_metadata('training_duration', 120.5)
        
        # Sauvegarder dans un fichier temporaire
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pkl') as f:
            temp_path = f.name
        
        try:
            registry1.save(temp_path)
            
            # Vérifier que le fichier existe
            assert os.path.exists(temp_path)
            
            # Charger le registre
            registry2 = ModelRegistry.load(temp_path)
            
            # Vérifier que tout est identique
            assert registry2.version == registry1.version
            assert registry2.created_at == registry1.created_at
            assert len(registry2.models) == len(registry1.models)
            assert set(registry2.models.keys()) == set(registry1.models.keys())
            
            # Vérifier les modèles
            for model_name in registry1.models:
                model1_data = registry1.models[model_name]
                model2_data = registry2.models[model_name]
                
                assert model1_data['feature_columns'] == model2_data['feature_columns']
                assert model1_data['metrics'] == model2_data['metrics']
            
            # Vérifier les métadonnées
            assert registry2.get_metadata('training_duration') == 120.5
        
        finally:
            # Nettoyer
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_save_creates_directory(self):
        """Test que save crée le dossier parent si nécessaire."""
        registry = ModelRegistry()
        model = MockModel("test")
        registry.register('test', model, {'accuracy': 0.85})
        
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, 'subdir', 'model.pkl')
            registry.save(filepath)
            
            assert os.path.exists(filepath)
    
    def test_load_nonexistent_file(self):
        """Test le chargement d'un fichier inexistant."""
        with pytest.raises(FileNotFoundError):
            ModelRegistry.load('nonexistent.pkl')
    
    def test_metadata_operations(self):
        """Test les opérations sur les métadonnées."""
        registry = ModelRegistry()
        
        # Set metadata
        registry.set_metadata('key1', 'value1')
        registry.set_metadata('key2', 123)
        
        # Get metadata
        assert registry.get_metadata('key1') == 'value1'
        assert registry.get_metadata('key2') == 123
        assert registry.get_metadata('nonexistent', 'default') == 'default'
    
    def test_list_models(self):
        """Test la liste des modèles."""
        registry = ModelRegistry()
        
        assert registry.list_models() == []
        
        model1 = MockModel("win")
        model2 = MockModel("total")
        
        registry.register('win', model1, {})
        registry.register('total', model2, {})
        
        models = registry.list_models()
        assert len(models) == 2
        assert 'win' in models
        assert 'total' in models
    
    def test_print_summary(self, capsys):
        """Test l'affichage du résumé."""
        registry = ModelRegistry()
        model = MockModel("test")
        metrics = {'accuracy': 0.85, 'mae': 10.5}
        hyperparams = {'learning_rate': 0.1}
        
        registry.register('test', model, metrics, hyperparameters=hyperparams)
        registry.set_metadata('training_duration', 120.5)
        
        registry.print_summary()
        
        captured = capsys.readouterr()
        assert 'RÉSUMÉ DU REGISTRE' in captured.out
        assert 'test' in captured.out.lower()
        assert 'accuracy' in captured.out.lower()
        assert '0.8500' in captured.out
        assert 'learning_rate' in captured.out
        assert 'training_duration' in captured.out
    
    def test_repr(self):
        """Test la représentation string."""
        registry = ModelRegistry()
        model = MockModel("test")
        registry.register('test', model, {})
        
        repr_str = repr(registry)
        assert 'ModelRegistry' in repr_str
        assert 'test' in repr_str
        assert registry.version in repr_str


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
