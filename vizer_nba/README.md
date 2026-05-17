# 🏀 NBA Prediction Models - Système Unifié

Système de prédiction NBA consolidé avec architecture unifiée pour prédire les victoires et les totaux de points.

## 📋 Vue d'Ensemble

Ce projet utilise des modèles de machine learning (XGBoost) pour prédire:
- **Victoires**: Quelle équipe va gagner le match
- **Totaux**: Le nombre total de points marqués dans le match

### Architecture Consolidée

- **Un seul script d'entraînement** (`train.py`) pour tous les modèles
- **Un seul fichier de modèle** (`models/nba_model.pkl`) contenant tous les modèles
- **Interface unifiée** (`UnifiedPredictor`) pour toutes les prédictions

## 🚀 Installation

```bash
# Créer un environnement virtuel
python -m venv venv
source venv/bin/activate

# Installer les dépendances
pip install -r requirements.txt
```

## 📊 Structure du Projet

```
NBA/
├── train.py                    # Script d'entraînement unifié
├── predict_json.py             # Prédictions en JSON
├── predict_today.py            # Prédictions des matchs du jour
├── config.yaml                 # Configuration centralisée
├── models/
│   └── nba_model.pkl          # Modèle unifié (tous les modèles)
├── src/
│   ├── data/                  # Chargement des données
│   ├── features/              # Feature engineering
│   ├── models/                # Modèles (base, registry, predictors)
│   └── api/                   # Interface de prédiction unifiée
└── data/                      # Données CSV
```

## 🎯 Utilisation

### 1. Entraîner les Modèles

```bash
python train.py
```

**Performances actuelles:**
- Modèle de victoire: 90.6% de précision (test sur saison 2025-26)
- Modèle de total: MAE de 7.48 points (test sur saison 2025-26)

### 2. Faire des Prédictions

```bash
# Prédire un match
python predict_json.py LAL:GSW --pretty

# Avec une ligne de total
python predict_json.py LAL:GSW --lines 220.5 --pretty

# Prédire tous les matchs du jour
python predict_today.py
```

### 3. Utiliser l'API Python

```python
from src.api.unified_predictor import UnifiedPredictor

# Charger le prédicteur
predictor = UnifiedPredictor('models/nba_model.pkl')

# Prédire le vainqueur
win_pred = predictor.predict_win('LAL', 'GSW')
print(f"Probabilité victoire domicile: {win_pred['home_win_proba']:.1%}")

# Prédire le total
total_pred = predictor.predict_total('LAL', 'GSW')
print(f"Total prédit: {total_pred['prediction']:.1f} points")

# Prédire under/over
uo_pred = predictor.predict_under_over('LAL', 'GSW', line=220.5)
print(f"Recommandation: {uo_pred['recommendation']}")

# Toutes les prédictions en une fois
all_pred = predictor.predict_all('LAL', 'GSW')
```

## 🔧 Configuration

Le fichier `config.yaml` contient tous les paramètres configurables (chemins, hyperparamètres, etc.).

## 📦 Structure du Modèle Unifié

Le fichier `models/nba_model.pkl` contient un registre avec tous les modèles:

```python
{
    'version': '1.0.0',
    'models': {
        'win': {...},    # Modèle de victoire
        'total': {...}   # Modèle de total
    },
    'metadata': {...}
}
```

## 📈 Features Utilisées

- Moyennes mobiles (5, 10, 20 derniers matchs): FG%, 3P%, FT%, rebonds, assists, etc.
- Splits domicile/extérieur
- Jours de repos entre matchs
- Séries de victoires/défaites

## 🧪 Tests

```bash
pytest tests/
```

## 📝 Notes

- Les données sont chargées depuis `data/*.csv`
- Les modèles sont entraînés sur les saisons 2000-2025
- Le test est effectué sur la saison 2025-26 en cours
- Le système utilise un split temporel pour éviter le data leakage
