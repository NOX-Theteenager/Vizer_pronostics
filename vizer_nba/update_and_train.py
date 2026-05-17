#!/usr/bin/env python
"""
Script automatique de mise à jour et d'entraînement des modèles NBA.

Ce script exécute automatiquement:
1. Récupération des données (équipes, joueurs, matchs)
2. Validation des datasets
3. Entraînement des modèles
4. Sauvegarde du modèle unifié

Usage:
    python update_and_train.py                    # Mise à jour complète
    python update_and_train.py --skip-fetch       # Entraînement seulement
    python update_and_train.py --fetch-only       # Récupération seulement
"""
import sys
import subprocess
import argparse
from pathlib import Path
from datetime import datetime


def print_section(title):
    """Affiche un titre de section."""
    print()
    print("=" * 70)
    print(f"🏀 {title}")
    print("=" * 70)
    print()


def run_command(cmd, description, cwd=None):
    """
    Exécute une commande et affiche le résultat.
    
    Args:
        cmd: Commande à exécuter (liste)
        description: Description de l'étape
        cwd: Répertoire de travail (optionnel)
        
    Returns:
        True si succès, False sinon
    """
    print(f"▶ {description}...")
    print(f"  Commande: {' '.join(cmd)}")
    print()
    
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            check=True,
            capture_output=False,
            text=True
        )
        print(f"✓ {description} - Terminé")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ {description} - Échec (code {e.returncode})")
        return False
    except Exception as e:
        print(f"✗ {description} - Erreur: {e}")
        return False


def fetch_data():
    """Récupère toutes les données NBA."""
    print_section("ÉTAPE 1/3: RÉCUPÉRATION DES DONNÉES")
    
    scripts_dir = Path("scripts")
    
    # 1. Équipes
    if not run_command(
        [sys.executable, "scripts/fetch_nba_teams.py"],
        "Récupération des équipes NBA"
    ):
        return False
    
    print()
    
    # 2. Joueurs
    if not run_command(
        [sys.executable, "scripts/fetch_nba_players.py"],
        "Récupération des joueurs NBA"
    ):
        return False
    
    print()
    
    # 3. Matchs
    if not run_command(
        [sys.executable, "scripts/fetch_nba_games.py"],
        "Récupération des matchs NBA (2000-2026)"
    ):
        return False
    
    print()
    print("✅ Toutes les données ont été récupérées avec succès")
    return True


def validate_data():
    """Valide les datasets récupérés."""
    print_section("ÉTAPE 2/3: VALIDATION DES DONNÉES")
    
    if not run_command(
        [sys.executable, "scripts/validate_datasets.py"],
        "Validation des datasets"
    ):
        print("⚠️  Avertissement: La validation a échoué, mais on continue...")
        return True  # On continue même si la validation échoue
    
    print()
    print("✅ Données validées")
    return True


def train_models(full_training=True):
    """
    Entraîne tous les modèles.
    
    Args:
        full_training: Si True, entraîne sur 100% des données (production)
                      Si False, entraîne avec split test (évaluation)
    """
    print_section("ÉTAPE 3/3: ENTRAÎNEMENT DES MODÈLES")
    
    script = "train_full.py" if full_training else "train.py"
    description = "Entraînement complet (100% des données)" if full_training else "Entraînement avec split test"
    
    if not run_command(
        [sys.executable, script],
        description
    ):
        return False
    
    print()
    print("✅ Modèles entraînés et sauvegardés")
    return True


def main():
    """Pipeline complet de mise à jour et d'entraînement."""
    parser = argparse.ArgumentParser(
        description="Mise à jour automatique des données et entraînement des modèles NBA"
    )
    parser.add_argument(
        '--skip-fetch',
        action='store_true',
        help="Sauter la récupération des données (entraînement seulement)"
    )
    parser.add_argument(
        '--fetch-only',
        action='store_true',
        help="Récupération des données seulement (pas d'entraînement)"
    )
    parser.add_argument(
        '--skip-validation',
        action='store_true',
        help="Sauter la validation des données"
    )
    parser.add_argument(
        '--test-mode',
        action='store_true',
        help="Mode test: entraîne avec split test au lieu de 100%% des données"
    )
    
    args = parser.parse_args()
    
    start_time = datetime.now()
    
    print()
    print("=" * 70)
    print("🏀 PIPELINE AUTOMATIQUE NBA - MISE À JOUR ET ENTRAÎNEMENT")
    print("=" * 70)
    print(f"Démarré le: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    if args.test_mode:
        print("Mode: TEST (avec split test)")
    else:
        print("Mode: PRODUCTION (100% des données)")
    
    print()
    
    # Vérifier qu'on est dans le bon répertoire
    if not Path("train.py").exists():
        print("✗ Erreur: Ce script doit être exécuté depuis la racine du projet")
        return 1
    
    success = True
    
    # Étape 1: Récupération des données
    if not args.skip_fetch:
        if not fetch_data():
            print()
            print("✗ Échec lors de la récupération des données")
            return 1
    else:
        print()
        print("⊘ Récupération des données ignorée (--skip-fetch)")
    
    # Étape 2: Validation
    if not args.skip_validation and not args.fetch_only:
        if not validate_data():
            print()
            print("✗ Échec lors de la validation des données")
            return 1
    else:
        if args.skip_validation:
            print()
            print("⊘ Validation des données ignorée (--skip-validation)")
    
    # Étape 3: Entraînement
    if not args.fetch_only:
        if not train_models(full_training=not args.test_mode):
            print()
            print("✗ Échec lors de l'entraînement des modèles")
            return 1
    else:
        print()
        print("⊘ Entraînement ignoré (--fetch-only)")
    
    # Résumé final
    end_time = datetime.now()
    duration = end_time - start_time
    
    print()
    print("=" * 70)
    print("✅ PIPELINE TERMINÉ AVEC SUCCÈS")
    print("=" * 70)
    print(f"Durée totale: {duration}")
    print(f"Terminé le: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    if not args.fetch_only:
        print("📊 Modèle sauvegardé: models/nba_model.pkl")
        print()
        print("Vous pouvez maintenant faire des prédictions avec:")
        print("  python predict_json.py \"LAL:GSW\" --pretty")
        print("  python predict_today.py")
        print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
