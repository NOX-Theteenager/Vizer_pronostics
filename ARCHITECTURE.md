# Architecture Commune Vizer — NBA & NHL

> Document de référence : design avant code. À relire avant chaque ajout structurel.

## 1. Objectifs

1. **Cohérence** — un développeur (toi ou Claude) qui ouvre `vizer_nba/` ou `vizer_nhl/` retrouve les mêmes scripts, les mêmes classes, les mêmes conventions.
2. **Extensibilité par marché** — ajouter un marché de paris = ajouter un fichier, pas refactorer un pipeline.
3. **Configuration externe** — aucun hyperparamètre, seuil, ou chemin hardcodé dans les scripts. Tout dans `config.yaml`.
4. **Reproductibilité** — pipeline déterministe et lançable en une commande.
5. **Backtest natif** — les prédictions historiques sont conservées dans un format commun pour permettre du ROI par marché.

## 2. Principe directeur

**Squelette identique, contenu spécifique.** Les sports diffèrent par leurs features, leurs API sources, et leurs marchés disponibles. Ils ne diffèrent pas par leur architecture.

## 3. Structure de dossiers (identique pour les deux sports)

```
vizer_<sport>/
├── config.yaml                         # Source unique de vérité
├── data/                               # CSVs sources, jamais modifiés en place
├── models/
│   └── <sport>_model.joblib            # Registre unifié
├── predictions/
│   └── YYYY-MM-DD.json                 # Historique horodaté
├── logs/
├── src/
│   ├── data/loader.py                  # Charge et valide
│   ├── features/engineer.py            # Feature engineering
│   ├── models/markets/                 # Un fichier par marché actif
│   │   ├── moneyline.py
│   │   ├── total.py
│   │   ├── period_total.py             # P1 NHL / Q1 NBA
│   │   └── ...
│   ├── api/external/                   # Appels API externes (avec fallback)
│   └── utils/                          # Helpers spécifiques au sport
├── scripts/                            # Fetch et validation des données
├── train.py                            # Avec split test (évaluation)
├── train_full.py                       # Sur 100% des données (production)
├── update_and_train.py                 # Orchestrateur
├── predict_today.py
└── predict_json.py
```

## 4. Le package `vizer_core/`

Code partagé strictement par les deux sports. **Aucune logique métier dedans**, uniquement des abstractions.

```
vizer_core/
├── base_predictor.py        # BasePredictor (un modèle ML)
├── market_base.py           # MarketBase + MarketPrediction + ValueBet
├── model_registry.py        # ModelRegistry (conteneur unifié)
├── unified_predictor.py     # UnifiedPredictor (façade)
├── config_loader.py         # Charge et valide config.yaml
└── math_utils.py            # Poisson, Bayesian, Kelly, Elo génériques
```

## 5. Hiérarchie conceptuelle

```
ModelRegistry
  └─ N x MarketBase (un par marché : moneyline, total, P1, BTTS, ...)
        └─ M x BasePredictor (un ou plusieurs modèles ML sous-jacents)
              └─ XGBoost / LightGBM / Poisson / Ordinal / Bayesian
```

Une `Market` produit une `MarketPrediction`. L'`UnifiedPredictor` interroge plusieurs marchés en une seule passe et retourne un dict `{market_name: MarketPrediction}`.

## 6. Contrats des classes (signatures)

### `BasePredictor` — abstraction d'un modèle ML

| Méthode | Type | Description |
|---|---|---|
| `fit(X_train, y_train, X_test=None, y_test=None) -> dict` | abstract | Entraîne. Retourne les métriques. |
| `predict(X) -> np.ndarray` | abstract | Prédiction ponctuelle. |
| `predict_proba(X) -> np.ndarray` | optional | Probabilités (classification). |
| `feature_names: list[str]` | property | Noms des features attendues. |
| `feature_importances() -> dict[str, float]` | optional | Pour debug. |
| `save(path) / load(path)` | mixin | Persistance. |

### `MarketBase` — abstraction d'un marché de paris

| Méthode | Type | Description |
|---|---|---|
| `name: str` | property | Identifiant du marché. |
| `enabled: bool` | property | Lu depuis config. |
| `fit(features_df, target_df) -> dict` | abstract | Entraîne les predictors internes. |
| `predict(home, away, context: dict) -> MarketPrediction` | abstract | Prédiction pour un match. |
| `value_bet(prediction, odds: float, **opts) -> ValueBet \| None` | concrete | Calcule l'edge et la mise Kelly. |
| `hyperparameters: dict` | property | Lu depuis config. |

### `MarketPrediction` — dataclass de sortie

```python
@dataclass
class MarketPrediction:
    market_name: str
    probabilities: dict[str, float]    # ex: {'home': 0.62, 'away': 0.38}
    expected_value: float | None       # ex: total prédit en points
    confidence: Literal['high', 'medium', 'low']
    metadata: dict                     # libre par marché (λ Poisson, etc.)
```

### `ValueBet` — dataclass de pari à valeur

```python
@dataclass
class ValueBet:
    market_name: str
    selection: str                     # 'home', 'over', '0-2 buts', ...
    predicted_proba: float
    bookmaker_odds: float
    implied_proba: float
    edge: float                        # predicted - implied
    kelly_stake: float                 # fraction du bankroll (déjà × kelly_factor)
    confidence: Literal['high', 'medium', 'low']
```

### `ModelRegistry` — conteneur unifié

| Méthode | Description |
|---|---|
| `register(market: MarketBase)` | Ajoute un marché au registre. |
| `get(name) -> MarketBase` | Récupère un marché par nom. |
| `list_markets() -> list[str]` | Liste les marchés actifs. |
| `set_metadata(key, value) / get_metadata(key)` | Métadonnées libres (durée, n_train, etc.). |
| `save(path) / load(path)` | Persistance via joblib. |
| `print_summary()` | Résumé console. |

### `UnifiedPredictor` — façade

| Méthode | Description |
|---|---|
| `__init__(registry_path, config_path)` | Charge le registre et la config. |
| `predict(home, away, markets=None, context=None) -> dict[str, MarketPrediction]` | Prédiction multi-marchés. |
| `value_bets(home, away, odds: dict) -> list[ValueBet]` | Filtre les value bets selon seuils config. |

## 7. Configuration commune (`config.yaml`)

Un seul schéma, valide pour les deux sports. Les sections inutiles à un sport sont simplement omises ou désactivées via `enabled: false`.

Voir `config.template.yaml` pour le modèle complet.

**Règle dure :** aucun script ne hardcode de paramètre présent dans `config.yaml`. Si ce n'est pas dans la config, c'est un bug.

## 8. Convention de nommage

| Concept | Convention |
|---|---|
| Fichier de marché | `src/models/markets/<market_name>.py` |
| Classe de marché | `class <MarketName>Market(MarketBase)` |
| Identifiant marché | `moneyline`, `total`, `period_total`, `btts`, `spread`, `interval`, `exact_score` |
| Saison | `season_id` (int) — format à documenter par sport |
| Équipe | abréviation 3 lettres (`LAL`, `GSW`, `MTL`, ...) |
| Match | `game_id` (str) |

## 9. Flow de données

```
fetch_data.py
    ↓
data/*.csv (sources)
    ↓
loader.py (charge + valide)
    ↓
engineer.py (features)
    ↓
train.py / train_full.py
    ↓ pour chaque marché actif :
    market.fit() → BasePredictor.fit()
    ↓
ModelRegistry.save() → models/<sport>_model.joblib
    ↓
predict_today.py / predict_json.py
    ↓
UnifiedPredictor.predict()
    ↓
predictions/YYYY-MM-DD.json
    ↓
backtesting/ (futur)
```

## 10. Plan de migration

| # | Étape | Sport | Estimation | Bloque ? |
|---|---|---|---|---|
| 0 | Architecture + scaffolding `vizer_core/` | commun | 1 session | — |
| 1 | Corriger bugs NBA (90.6%, double save, config inutilisée) | NBA | 1 session | Oui pour suite |
| 2 | Refactor NBA vers squelette cible | NBA | 1-2 sessions | Non |
| 3 | Migrer NHL des notebooks vers scripts | NHL | 2-3 sessions | Non |
| 4 | Module backtest commun | commun | 1 session | Non |
| 5 | Enrichir marchés NBA (spread, Q1 total) | NBA | 1 session | Non |

## 11. Décisions de design explicites

- **Pas de monorepo** : `vizer_nba/` et `vizer_nhl/` restent séparés. `vizer_core/` est soit dupliqué soit installé comme package local (`pip install -e ../vizer_core`). À trancher à l'étape 2.
- **Joblib pour la persistance** : pas de pickle direct. Une seule extension : `.joblib`.
- **Pas de framework lourd** : pas de MLflow, pas d'Airflow. Scripts Python + YAML + joblib suffisent à cette échelle.
- **Tests unitaires sur `vizer_core/` uniquement au démarrage** : la logique métier des sports sera testée par backtest plus tard.

## 12. Ce qui n'est PAS dans `vizer_core/`

À garder strictement spécifique au sport, pour éviter les abstractions prématurées :

- Feature engineering (NBA et NHL ont des features très différentes)
- Logique d'API externe (NHL API, NBA API, Moneypuck, Odds API)
- Détection de gardiens partants (NHL only)
- Conventions de saison (`SEASON_ID` NBA vs `season` NHL)
- Le contenu des features (par contre les *types* de transformations comme rolling windows peuvent être génériques)
