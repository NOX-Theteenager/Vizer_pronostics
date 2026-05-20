# 📁 Vizer NHL — Datasets

Ce dossier contient **tous les fichiers de données** utilisés par le pipeline
NHL. Il sert d'entrée commune aux notebooks d'agrégation (01-02b) ET aux
scripts Python du nouveau pipeline `vizer_nhl/`.

> ⚠️ **Aucun de ces fichiers n'est dans git** (cf. `.gitignore`).
> Ils sont volumineux (centaines de Mo cumulés) et publics — chacun les
> télécharge depuis sa propre source. Voir section "Reproductibilité" plus bas.

---

## 🗂️ Inventaire des fichiers

### Données brutes Moneypuck (entrée des notebooks 01-02)

Source : <https://moneypuck.com/data.htm> (rubrique "Player and Team Stats").

| Fichier | Taille | Description |
|---|---|---|
| `all_teams.csv` | ~50 Mo | Stats équipes game-by-game 2008-aujourd'hui. Inclut situations 5v5, all, 5on4 (PP), 4on5 (PK). Mise à jour quotidienne durant la saison. |
| `goalies_2008_2024.csv` | ~10 Mo | Stats gardiens historique. xGoals, goals, GSAE par match. |
| `goalies_2025.csv` | ~1 Mo | Stats gardiens saison courante. |
| `skaters_2008_2024.csv` | ~200 Mo | Stats joueurs de champ historique (top-line xGF, takeaways, penalties). |
| `skaters_2025.csv` | ~5 Mo | Stats joueurs saison courante. |
| `lines_2008_2024.csv` | ~80 Mo | Stats par ligne (forward lines). |
| `lines_2025.csv` | ~5 Mo | Stats par ligne saison courante. |
| `shots_2007-2024.csv` | ~400 Mo | Play-by-play shots historique. Utilisé uniquement par 02b_Period_Data. |
| `shots_2025.csv` | ~10 Mo | Play-by-play shots saison courante. |

### Fichiers intermédiaires (générés par les notebooks)

| Fichier | Source | Description |
|---|---|---|
| `period_stats.csv` | 02b_Period_Data.ipynb | Stats par période (P1/P2/P3) agrégées depuis les shots. Inclut CSA% (Score-Adjusted Corsi). Optionnel — si absent, le pipeline utilise approximation λ_p1 = λ_total × 0.30. |
| `h2h_lookup.json` | 02_Agregation.ipynb | Cache des head-to-head historiques (dominance + scoring trend). |
| `goalies_rolling.csv` | 02_Agregation.ipynb | Stats gardiens rolling pré-calculées pour lookup à l'inférence. |

### Dataset final agrégé (sortie du pipeline 01-02)

| Fichier | Source | Description |
|---|---|---|
| **`dataset_agrege_vizer_nhl.csv`** | 02_Agregation.ipynb (sortie finale) | **ENTRÉE PRINCIPALE** du nouveau pipeline `vizer_nhl/`. Contient une ligne par match avec toutes les features rolling (windows 5/10/20/50), les targets (`home_team_won`, `finalGoals_home/away`), et optionnellement les colonnes P1 (`goals_p1_home/away`). |

---

## 🔄 Reproductibilité — comment obtenir les données

### Option 1 : Téléchargement complet (premier setup)

```bash
# Lancer le notebook 01_Maintenance.ipynb qui télécharge automatiquement
# tous les CSVs Moneypuck nécessaires depuis https://moneypuck.com/data.htm

cd ~/Documents/Projets/Vizer_pronostics/vizer_nhl
jupyter notebook ../notebooks/01_Maintenance.ipynb
# Exécuter toutes les cellules → remplit data/ avec les CSVs bruts
```

### Option 2 : Mise à jour incrémentale (saison courante)

Le notebook 01 sait détecter quels fichiers existent déjà et ne télécharge
que les fichiers `*_2025.csv` (saison courante) ou plus récente.

### Option 3 : Agrégation finale uniquement

Si tu as déjà les CSVs bruts :

```bash
jupyter notebook ../notebooks/02_Agregation.ipynb
# Produit : data/dataset_agrege_vizer_nhl.csv (~80 Mo)
```

---

## 🚀 Utilisation par le pipeline `vizer_nhl/`

Les scripts Python ne lisent que **`dataset_agrege_vizer_nhl.csv`**.
Les notebooks 01-02 restent responsables de la chaîne d'agrégation Moneypuck.

```python
from src.data.loader import NHLDataLoader

loader = NHLDataLoader(
    data_dir='data',
    filename='dataset_agrege_vizer_nhl.csv',
)
df = loader.load(exclude_anomalous_seasons=True)
```

Cette séparation a un intérêt : les notebooks gèrent la complexité Moneypuck
(téléchargements, parsing CSV de 400 Mo, agrégations rolling) tandis que le
pipeline `vizer_nhl/` reste léger et focalisé sur l'entraînement / inférence.

---

## 📊 Format du dataset final

Voir `src/data/loader.py` (section `REQUIRED_META_COLS`) pour la liste exacte
des colonnes attendues. Récapitulatif rapide :

```
Méta (obligatoires) :
    gameId_home, gameDate_home, team_home, team_away

Cibles (obligatoires) :
    home_team_won (0/1, les SO sont arrondis)
    finalGoals_home, finalGoals_away

Cibles P1 (optionnelles) :
    goals_p1_home, goals_p1_away

Features _home/_away (toutes optionnelles, le pipeline détecte celles présentes) :
    avg_xGF_pct_{5,10,20,50}_*
    avg_pp_{5,10,20}_*, avg_pk_10_*
    avg_HDcf_10_*, avg_panic_score_10_*, avg_corsi_10_*, avg_pdo_10_*
    avg_top_line_xGF_10_*, avg_GSAE_10_*
    Forme_5_matchs_*, momentum_*
    is_back_to_back_*, days_rest_*, stress_score_*

Diffs déjà calculés (optionnels — recomputés si absents) :
    diff_xGF_pct, diff_top_line_xGF, diff_pp, diff_forme, diff_b2b,
    diff_HDcf, diff_panic_score, diff_pdo, diff_momentum, ...
```

---

## 🧹 Nettoyage et maintenance

### Forcer la mise à jour de la saison courante

```bash
rm data/goalies_2025.csv data/skaters_2025.csv data/lines_2025.csv
# Relancer 01_Maintenance.ipynb → re-télécharge uniquement les fichiers manquants
```

### Espace disque attendu

```
Total brut Moneypuck    : ~750 Mo
Dataset agrégé final    : ~80 Mo
Caches intermédiaires   : ~50 Mo
TOTAL                   : ~880 Mo
```

Si l'espace est critique, tu peux supprimer `shots_2007-2024.csv` (400 Mo)
**après** avoir généré `period_stats.csv` une fois.
