#!/usr/bin/env python
"""
Script d'entraînement COMPLET pour tous les modèles NBA.

Ce script entraîne les modèles sur 100% des données disponibles (pas de split test).
Utilisé pour la production afin d'avoir le modèle le plus à jour possible.

Pipeline:
1. Charge toutes les données disponibles
2. Effectue le feature engineering
3. Entraîne sur 100% des données (pas de test set)
4. Sauvegarde le modèle unifié dans models/nba_model.pkl

Usage:
    python train_full.py
"""
import sys
import time
from datetime import datetime

from src.data.loader import NBADataLoader
from src.features.engineer import MatchFeatureEngineer
from src.models.win_predictor import NBAMatchPredictor
from src.models.total_predictor import NBATotalPredictor
from src.models.registry import ModelRegistry


def main():
    """Pipeline d'entraînement complet (100% des données) pour tous les modèles NBA."""
    start_time = time.time()
    
    print("=" * 70)
    print("🏀 ENTRAÎNEMENT COMPLET DES MODÈLES NBA (100% DES DONNÉES)")
    print("=" * 70)
    print(f"Démarré le: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("⚠️  Mode PRODUCTION: Entraînement sur toutes les données disponibles")
    print("   (pas de split test - modèle le plus à jour possible)")
    print()
    
    # ========================================================================
    # 1. CHARGEMENT DES DONNÉES
    # ========================================================================
    print("📂 Étape 1/5: Chargement des données...")
    print("-" * 70)
    try:
        loader = NBADataLoader()
        games = loader.load_games()
        print(f"  ✓ {len(games):,} matchs chargés (toutes saisons disponibles)")
        print()
    except Exception as e:
        print(f"  ✗ Erreur lors du chargement des données: {e}")
        return 1
    
    # ========================================================================
    # 2. FEATURE ENGINEERING
    # ========================================================================
    print("🔧 Étape 2/5: Feature Engineering...")
    print("-" * 70)
    try:
        engineer = MatchFeatureEngineer(windows=[5, 10, 20])
        features_df = engineer.create_features(games, include_h2h=False)
        
        # Ajouter la colonne TOTAL_PTS pour le modèle de totaux
        features_df['TOTAL_PTS'] = features_df['HOME_PTS'] + features_df['AWAY_PTS']
        
        print(f"  ✓ Features créées pour {len(features_df):,} matchs")
        print()
    except Exception as e:
        print(f"  ✗ Erreur lors du feature engineering: {e}")
        return 1
    
    # ========================================================================
    # 3. PRÉPARATION DES DONNÉES (100% pour l'entraînement)
    # ========================================================================
    print("📊 Étape 3/5: Préparation des données...")
    print("-" * 70)
    
    # Utiliser TOUTES les données pour l'entraînement
    train_df = features_df.copy()
    
    print(f"  Entraînement: {len(train_df):,} matchs (100% des données)")
    print(f"  Saisons: {train_df['SEASON_ID'].min()} à {train_df['SEASON_ID'].max()}")
    print()
    
    # ========================================================================
    # 4. ENTRAÎNEMENT DE TOUS LES MODÈLES
    # ========================================================================
    print("🎯 Étape 4/5: Entraînement de tous les modèles...")
    print("=" * 70)
    
    # Créer le registre
    registry = ModelRegistry()
    
    # ========================================================================
    # 4.1. MODÈLE DE VICTOIRE
    # ========================================================================
    print()
    print("🏆 Modèle 1/2: Prédiction de Victoire")
    print("-" * 70)
    
    try:
        # Entraîner (la méthode train() gère la préparation des features en interne)
        win_predictor = NBAMatchPredictor()
        
        # Pour l'entraînement complet, on passe le même DataFrame pour train et test
        # (le test ne sera pas utilisé, mais la méthode l'attend)
        win_metrics = win_predictor.train(train_df, train_df, verbose=True)
        
        # Enregistrer dans le registre
        registry.register(
            model_name='win',
            model=win_predictor,
            metrics=win_metrics,
            hyperparameters={
                'n_estimators': 200,
                'max_depth': 6,
                'learning_rate': 0.1
            }
        )
        
        print("✓ Modèle de victoire enregistré")
        
    except Exception as e:
        print(f"✗ Erreur lors de l'entraînement du modèle de victoire: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # ========================================================================
    # 4.2. MODÈLE DE TOTAL
    # ========================================================================
    print()
    print("📊 Modèle 2/2: Prédiction de Total")
    print("-" * 70)
    
    try:
        # Entraîner (la méthode train() gère la préparation des features en interne)
        total_predictor = NBATotalPredictor()
        
        # Pour l'entraînement complet, on passe le même DataFrame pour train et test
        total_metrics = total_predictor.train(train_df, train_df, verbose=True)
        
        # Enregistrer dans le registre
        registry.register(
            model_name='total',
            model=total_predictor,
            metrics=total_metrics,
            hyperparameters={
                'n_estimators': 200,
                'max_depth': 6,
                'learning_rate': 0.1
            }
        )
        
        print("✓ Modèle de total enregistré")
        
    except Exception as e:
        print(f"✗ Erreur lors de l'entraînement du modèle de total: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # ========================================================================
    # 5. SAUVEGARDE DU REGISTRE
    # ========================================================================
    print()
    print("💾 Étape 5/5: Sauvegarde du registre unifié...")
    print("-" * 70)
    
    try:
        output_path = 'models/nba_model.pkl'
        registry.save(output_path)
        
        import os
        file_size = os.path.getsize(output_path) / (1024 * 1024)
        print(f"  ✓ Registre sauvegardé: {output_path}")
        print(f"  ✓ Taille: {file_size:.1f} MB")
        print()
        
    except Exception as e:
        print(f"  ✗ Erreur lors de la sauvegarde: {e}")
        return 1
    
    # ========================================================================
    # RÉSUMÉ FINAL
    # ========================================================================
    elapsed = time.time() - start_time
    
    print()
    print("=" * 70)
    print("✅ ENTRAÎNEMENT COMPLET TERMINÉ")
    print("=" * 70)
    print(f"Durée totale: {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print()
    print("📊 Résumé:")
    print(f"  • Modèles entraînés sur {len(train_df):,} matchs")
    print(f"  • Fichier: {output_path} ({file_size:.1f} MB)")
    print()
    print("🎯 Le modèle est prêt pour la production!")
    print()
    print("Exemples d'utilisation:")
    print("  python predict_json.py \"LAL:GSW\" --pretty")
    print("  python predict_today.py")
    print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
