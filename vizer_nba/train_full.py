#!/usr/bin/env python3
"""
train_full.py — Entraînement NBA de production.

Délègue à train.py en mode `--full` : même architecture MarketBase, même
config.yaml, même registre vizer_core.ModelRegistry, mais entraîné sur la
fenêtre de saisons la plus récente (saison courante incluse) et sans jeu de
test.

Historique — pourquoi ce fichier n'est plus qu'un aiguillage :
    Jusqu'au 2026-10-06, train_full.py était une implémentation parallèle,
    antérieure au refactor MarketBase. Elle produisait un registre au format
    legacy ({version, created_at, models, metadata}) que
    vizer_core.ModelRegistry.load() refuse, et n'entraînait que 2 modèles
    ('win', 'total') au lieu des 5 marchés de config.yaml. Comme c'est ce
    script que le pipeline Kaggle exécute, le modèle déployé chaque semaine
    était inutilisable par predict_all.py. Elle entraînait de surcroît sur les
    25 saisons disponibles, ignorant le train_window de la config qui existe
    précisément pour écarter les saisons pré-COVID (distribution shift).

    Il n'y a donc plus qu'un seul chemin d'entraînement, et les deux modes se
    distinguent par un flag.

Usage :
    python train_full.py                  # production (équivaut à train.py --full)
    python train_full.py -c autre.yaml

Métriques : en mode production il n'y a pas de jeu de test, donc les métriques
enregistrées dans le registre sont in-sample. Le registre le signale via
metadata['metrics_in_sample'] = True. Pour des chiffres de généralisation,
lancer `python train.py` (mode split).
"""
import sys

from train import main

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Entraînement NBA de production (100% de la fenêtre récente)"
    )
    parser.add_argument('-c', '--config', default='config.yaml')
    args = parser.parse_args()
    sys.exit(main(config_path=args.config, full=True))
