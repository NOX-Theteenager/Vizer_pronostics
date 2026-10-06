#!/usr/bin/env python
"""
train_full.py — Entraînement NHL de production.

Délègue à train.py en mode `--full` : même config, mêmes engines, mêmes
markets, mais entraîné sur 100% des matchs du dataset agrégé, sans jeu de test.

Pourquoi ce fichier existe :
    Jusqu'au 2026-10-06, NHL n'avait que train.py, qui réserve la dernière
    saison pour l'évaluation. Le modèle déployé chaque lundi n'avait donc
    jamais vu la saison en cours — l'écart grandissait semaine après semaine
    pendant que le pipeline tournait. ARCHITECTURE.md prévoyait ce script
    (§3 : « train_full.py — Sur 100% des données (production) ») ; il manquait.

Usage :
    python train_full.py
    python train_full.py --output models/nhl_model.pkl
    python train_full.py --markets moneyline total btts

Métriques : sans jeu de test, les métriques du registre sont in-sample et
metadata['metrics_in_sample'] vaut True. Pour des chiffres de généralisation,
lancer `python train.py` (mode split).
"""
import sys

from train import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] + ['--full']))
