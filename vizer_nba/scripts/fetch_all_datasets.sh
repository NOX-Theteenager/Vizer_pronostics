#!/bin/bash

echo "=========================================="
echo "RÉCUPÉRATION DE TOUS LES DATASETS NBA"
echo "=========================================="
echo ""

# Activer l'environnement virtuel si nécessaire
if [ -d "venv" ]; then
    echo "Activation de l'environnement virtuel..."
    source venv/bin/activate
fi

# 1. Équipes (rapide - quelques secondes)
echo ""
echo "=========================================="
echo "1/4 - ÉQUIPES NBA"
echo "=========================================="
python scripts/fetch_nba_teams.py

if [ $? -ne 0 ]; then
    echo "✗ Erreur lors de la récupération des équipes"
    exit 1
fi

# 2. Joueurs (rapide - quelques secondes)
echo ""
echo "=========================================="
echo "2/4 - JOUEURS NBA"
echo "=========================================="
python scripts/fetch_nba_players.py

if [ $? -ne 0 ]; then
    echo "✗ Erreur lors de la récupération des joueurs"
    exit 1
fi

# 3. Matchs (moyen - 2-5 minutes selon les saisons)
echo ""
echo "=========================================="
echo "3/4 - MATCHS NBA (2000-2026)"
echo "=========================================="
python scripts/fetch_nba_games.py

if [ $? -ne 0 ]; then
    echo "✗ Erreur lors de la récupération des matchs"
    exit 1
fi

# 4. Stats joueurs par match (long - optionnel)
echo ""
echo "=========================================="
echo "4/4 - STATS JOUEURS PAR MATCH (OPTIONNEL)"
echo "=========================================="
echo ""
echo "⚠️  Cette étape peut prendre 30-60 minutes"
echo "Voulez-vous récupérer les stats des joueurs par match? (o/N)"
read -r response

if [[ "$response" =~ ^([oO][uU][iI]|[oO])$ ]]; then
    echo ""
    echo "Saisons à récupérer (par défaut: 2024-25 2025-26):"
    echo "Entrez les saisons séparées par des espaces, ou appuyez sur Entrée pour les saisons par défaut"
    read -r seasons
    
    if [ -z "$seasons" ]; then
        python scripts/fetch_nba_player_games.py
    else
        python scripts/fetch_nba_player_games.py --seasons $seasons
    fi
    
    if [ $? -ne 0 ]; then
        echo "✗ Erreur lors de la récupération des stats joueurs"
        exit 1
    fi
else
    echo "⊘ Stats joueurs par match ignorées"
fi

echo ""
echo "=========================================="
echo "✅ TOUS LES DATASETS RÉCUPÉRÉS"
echo "=========================================="
echo ""
echo "Datasets disponibles dans data/:"
ls -lh data/NBA_*.csv | grep -v OLD | grep -v backup
echo ""
