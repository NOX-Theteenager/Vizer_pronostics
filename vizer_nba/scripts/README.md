# Scripts de Récupération des Datasets NBA

Ce dossier contient tous les scripts pour récupérer les datasets NBA depuis l'API officielle.

## 🎯 Vue d'ensemble

Les scripts récupèrent les données brutes de l'API NBA sans modification. La structure des données est celle fournie directement par l'API.

## 📦 Datasets disponibles

| Dataset | Fichier | Description | Taille | Temps |
|---------|---------|-------------|--------|-------|
| **Équipes** | `NBA_TEAMS.csv` | Liste de toutes les équipes NBA | ~2 KB | 5 sec |
| **Joueurs** | `NBA_PLAYERS.csv` | Tous les joueurs (historique complet) | ~200 KB | 5 sec |
| **Joueurs actifs** | `NBA_ACTIVE_PLAYERS.csv` | Joueurs actifs uniquement | ~20 KB | 5 sec |
| **Matchs** | `NBA_GAMES.csv` | Tous les matchs 2000-2026 | ~10 MB | 2-5 min |
| **Stats joueurs** | `NBA_PLAYER_GAMES.csv` | Stats des joueurs par match | ~5 MB | 30-60 min |

## 🚀 Utilisation rapide

### Option 1: Tout récupérer (recommandé)
```bash
./scripts/fetch_all_datasets.sh
```

### Option 2: Datasets individuels

```bash
# Équipes NBA
python scripts/fetch_nba_teams.py

# Joueurs NBA
python scripts/fetch_nba_players.py

# Matchs NBA (2000-2026)
python scripts/fetch_nba_games.py

# Stats joueurs par match (2024-25 et 2025-26)
python scripts/fetch_nba_player_games.py

# Stats joueurs - saisons personnalisées
python scripts/fetch_nba_player_games.py --seasons 2020-21 2021-22 2022-23
```

## 📋 Scripts disponibles

### `fetch_nba_teams.py`
Récupère la liste complète des équipes NBA.

**Colonnes:**
- `id`: ID unique de l'équipe
- `full_name`: Nom complet (ex: "Los Angeles Lakers")
- `abbreviation`: Abréviation (ex: "LAL")
- `nickname`: Surnom (ex: "Lakers")
- `city`: Ville
- `state`: État
- `year_founded`: Année de fondation

### `fetch_nba_players.py`
Récupère tous les joueurs NBA (historique + actifs).

**Colonnes:**
- `id`: ID unique du joueur
- `full_name`: Nom complet
- `first_name`: Prénom
- `last_name`: Nom de famille
- `is_active`: Joueur actif (True/False)

**Sorties:**
- `NBA_PLAYERS.csv`: Tous les joueurs (~5000+)
- `NBA_ACTIVE_PLAYERS.csv`: Joueurs actifs uniquement (~500)

### `fetch_nba_games.py`
Récupère tous les matchs de saison régulière de 2000 à 2026.

**Caractéristiques:**
- ~30,000+ matchs (2 entrées par match, une par équipe)
- Toutes les stats de base par équipe
- Saisons: 2000-01 à 2025-26

**Colonnes principales:**
- `SEASON_ID`: ID de la saison
- `TEAM_ID`: ID de l'équipe
- `GAME_ID`: ID unique du match
- `GAME_DATE`: Date du match
- `MATCHUP`: Format "TEAM1 @ TEAM2" ou "TEAM1 vs. TEAM2"
- `WL`: Résultat (W/L)
- `PTS`: Points marqués
- `FGM`, `FGA`, `FG_PCT`: Tirs réussis/tentés/pourcentage
- `FG3M`, `FG3A`, `FG3_PCT`: Tirs 3pts
- `FTM`, `FTA`, `FT_PCT`: Lancers francs
- `REB`, `AST`, `STL`, `BLK`, `TOV`: Rebonds, passes, interceptions, contres, pertes
- `PLUS_MINUS`: +/- du match

### `fetch_nba_player_games.py`
Récupère les statistiques détaillées des joueurs par match.

**Options:**
```bash
# Saisons par défaut (2024-25, 2025-26)
python scripts/fetch_nba_player_games.py

# Saisons personnalisées
python scripts/fetch_nba_player_games.py --seasons 2020-21 2021-22 2022-23

# Tous les joueurs (pas seulement les actifs)
python scripts/fetch_nba_player_games.py --all-players
```

**Caractéristiques:**
- Sauvegarde intermédiaire tous les 50 joueurs
- Gestion des erreurs et retry
- Respect des limites de l'API (0.6s entre requêtes)

**Colonnes principales:**
- `SEASON_ID`: ID de la saison
- `Player_ID`: ID du joueur
- `Game_ID`: ID du match
- `GAME_DATE`: Date du match
- `MATCHUP`: Adversaire
- `WL`: Résultat
- `MIN`: Minutes jouées
- `PTS`: Points
- `FGM`, `FGA`, `FG_PCT`: Tirs
- `FG3M`, `FG3A`, `FG3_PCT`: Tirs 3pts
- `FTM`, `FTA`, `FT_PCT`: Lancers francs
- `REB`, `AST`, `STL`, `BLK`, `TOV`: Stats diverses
- `PLUS_MINUS`: +/- du joueur

## ⚙️ Configuration

### Modifier les saisons dans `fetch_nba_games.py`
```python
seasons = [
    '2020-21', '2021-22', '2022-23', '2023-24', '2024-25', '2025-26'
]
```

### Modifier les fenêtres de temps
Tous les scripts incluent des pauses (`time.sleep()`) pour respecter les limites de l'API:
- Matchs: 2 secondes entre saisons
- Stats joueurs: 0.6 secondes entre joueurs

## 🔒 Sauvegardes automatiques

Tous les scripts créent automatiquement une sauvegarde de l'ancien fichier avant de le remplacer:
```
data/NBA_GAMES_OLD_20260227_212601.csv
data/NBA_TEAMS_OLD_20260227_213045.csv
...
```

## 📊 Structure des données

Les données sont au format CSV avec:
- En-têtes en première ligne
- Séparateur: virgule (`,`)
- Encodage: UTF-8
- Pas de modification des noms de colonnes (structure brute de l'API)

## 🐛 Dépannage

### Erreur: "Rate limit exceeded"
L'API NBA a des limites. Solutions:
- Augmentez les délais dans les scripts (`time.sleep()`)
- Réessayez plus tard
- Pour les stats joueurs, utilisez `--seasons` pour limiter les saisons

### Erreur: "No data found"
- Vérifiez votre connexion internet
- Vérifiez que `nba_api` est installé: `pip install nba_api`
- L'API peut être temporairement indisponible

### Script interrompu
Pour les stats joueurs, un fichier temporaire est créé:
```bash
# Reprendre depuis le fichier temporaire
cp data/NBA_PLAYER_GAMES_TEMP.csv data/NBA_PLAYER_GAMES.csv
```

## 📝 Notes importantes

1. **Chaque match apparaît 2 fois** dans `NBA_GAMES.csv` (une fois par équipe)
2. **Playoffs non inclus** - saison régulière uniquement
3. **Données en temps réel** - les saisons en cours peuvent être incomplètes
4. **Structure brute** - aucune transformation des données de l'API
5. **Compatibilité** - les anciens codes devront être adaptés à la nouvelle structure

## 🔄 Mise à jour régulière

Pour mettre à jour les données pendant la saison:
```bash
# Mettre à jour uniquement les matchs récents
python scripts/fetch_nba_games.py

# Mettre à jour les stats des joueurs actifs
python scripts/fetch_nba_player_games.py --seasons 2025-26
```

## 📚 Ressources

- [nba_api Documentation](https://github.com/swar/nba_api)
- [NBA Stats API](https://stats.nba.com/)
