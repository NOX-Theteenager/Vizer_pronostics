# 🚀 Guide d'Utilisation Rapide

## Pipeline Automatique Complet

### Mise à jour et entraînement (recommandé)

```bash
# Pipeline complet: récupération des données + entraînement sur 100% des données
python update_and_train.py
```

Ce script exécute automatiquement:
1. Récupération des équipes NBA
2. Récupération des joueurs NBA
3. Récupération des matchs NBA (2000-2026)
4. Validation des données
5. Entraînement sur 100% des données disponibles
6. Sauvegarde du modèle dans `models/nba_model.pkl`

### Options disponibles

```bash
# Entraînement seulement (sans récupération des données)
python update_and_train.py --skip-fetch

# Récupération des données seulement (sans entraînement)
python update_and_train.py --fetch-only

# Mode test (avec split test au lieu de 100% des données)
python update_and_train.py --test-mode

# Sauter la validation
python update_and_train.py --skip-validation
```

## Scripts Individuels

### Entraînement

```bash
# Entraînement sur 100% des données (PRODUCTION)
python train_full.py

# Entraînement avec split test (ÉVALUATION)
python train.py
```

### Prédictions

```bash
# Prédire un match
python predict_json.py "LAL:GSW" --pretty

# Prédire avec une ligne de total
python predict_json.py "LAL:GSW" --lines 220.5 --pretty

# Prédire plusieurs matchs
python predict_json.py "LAL:GSW" "BOS:MIA" "MIL:PHI" --pretty

# Prédire les matchs du jour
python predict_today.py
```

## Workflow Recommandé

### Mise à jour quotidienne

```bash
# Chaque jour, mettre à jour les données et réentraîner
python update_and_train.py
```

### Prédictions

```bash
# 1. Mode interactif (le plus simple - recommandé)
python predict_today.py --interactive

# 2. Lister les matchs du jour pour planifier les lignes
python predict_today.py --list-only

# 3. Faire des prédictions avec les lignes planifiées
python predict_today.py --lines 0022500858:220.5 0022500859:215.0

# Ou sans lignes (juste victoire et total prédit)
python predict_today.py
```

### Workflow complet quotidien

```bash
# 1. Mettre à jour les données et réentraîner
python update_and_train.py

# 2. Mode interactif pour entrer les lignes et obtenir les prédictions
python predict_today.py --interactive

# 3. Consulter les résultats
cat predictions_today.json | jq
```

## Fréquence de Mise à Jour

- **Données**: Mettre à jour quotidiennement pour avoir les derniers matchs
- **Modèle**: Réentraîner après chaque mise à jour des données pour avoir les prédictions les plus précises

## Temps d'Exécution Estimé

- Récupération des données: ~2-5 minutes
- Entraînement complet: ~30-60 secondes
- **Total**: ~3-6 minutes pour le pipeline complet
