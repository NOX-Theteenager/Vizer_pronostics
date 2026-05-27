"""
Script pour récupérer TOUS les matchs NBA depuis 2020 jusqu'à 2026
Structure brute de l'API NBA - pas de modification
"""
import pandas as pd
import time
from datetime import datetime
from nba_api.stats.endpoints import leaguegamefinder
import sys

def fetch_all_games(incremental=True):
    """
    Récupère tous les matchs NBA de 2000 à 2026
    
    Args:
        incremental: Si True, ne télécharge que les nouvelles données
    """
    import os

    # Saisons à récupérer : générées DYNAMIQUEMENT de 2000-01 jusqu'à la
    # saison courante (incluse). Évite la liste figée qui empêchait la
    # récupération des nouvelles saisons après 2025-26.
    now = datetime.now()
    # Après juillet → la nouvelle saison (year-year+1) a démarré
    end_year = now.year if now.month >= 7 else now.year - 1
    all_seasons = [f"{y}-{str(y + 1)[-2:]}" for y in range(2000, end_year + 1)]
    
    existing_df = None
    seasons_to_fetch = all_seasons
    
    # Si mode incrémental, charger les données existantes
    if incremental and os.path.exists('data/NBA_GAMES.csv'):
        print("📂 Chargement des données existantes...")
        existing_df = pd.read_csv('data/NBA_GAMES.csv')
        existing_df['GAME_DATE'] = pd.to_datetime(existing_df['GAME_DATE'])
        
        last_date = existing_df['GAME_DATE'].max()
        print(f"✓ Dernière date: {last_date.date()}")
        print(f"✓ {len(existing_df):,} entrées existantes")
        
        # Déterminer quelles saisons ont besoin d'être mises à jour
        # On met à jour seulement la saison en cours et la suivante
        current_year = datetime.now().year
        current_month = datetime.now().month
        
        # Si on est après juillet, la nouvelle saison a commencé
        if current_month >= 7:
            current_season = f"{current_year}-{str(current_year + 1)[-2:]}"
        else:
            current_season = f"{current_year - 1}-{str(current_year)[-2:]}"
        
        # Trouver l'index de la saison actuelle
        try:
            current_idx = all_seasons.index(current_season)
            # Mettre à jour seulement la saison actuelle
            seasons_to_fetch = [current_season]
            print(f"📥 Mode incrémental: mise à jour de {current_season} uniquement")
        except ValueError:
            print(f"⚠️  Saison {current_season} non trouvée, téléchargement complet")
            seasons_to_fetch = all_seasons
        
        print()
    else:
        print("=" * 70)
        print("RÉCUPÉRATION COMPLÈTE DES MATCHS NBA")
        print("=" * 70)
        print(f"Saisons: {', '.join(all_seasons)}")
        print()
    
    all_games = []
    
    for season in seasons_to_fetch:
        print(f"📥 Récupération saison {season}...", end=" ", flush=True)
        
        try:
            # Récupérer tous les matchs de la saison régulière
            gamefinder = leaguegamefinder.LeagueGameFinder(
                season_nullable=season,
                season_type_nullable='Regular Season',
                league_id_nullable='00'
            )
            
            games_df = gamefinder.get_data_frames()[0]
            
            if not games_df.empty:
                all_games.append(games_df)
                print(f"✓ {len(games_df)} entrées")
            else:
                print("⚠ Aucune donnée")
                
        except Exception as e:
            print(f"✗ Erreur: {e}")
            continue
        
        # Pause pour respecter les limites de l'API
        time.sleep(2)
    
    if not all_games:
        if existing_df is not None:
            print("\n⚠️  Aucune nouvelle donnée, conservation des données existantes")
            return existing_df
        else:
            print("\n✗ Aucune donnée récupérée!")
            return None
    
    # Combiner les nouvelles données
    print("\n📊 Combinaison des données...")
    new_df = pd.concat(all_games, ignore_index=True)
    new_df['GAME_DATE'] = pd.to_datetime(new_df['GAME_DATE'])
    
    # Si mode incrémental, combiner avec les anciennes données
    if existing_df is not None:
        print("🔄 Fusion avec les données existantes...")
        
        # Supprimer les anciennes entrées de la saison mise à jour
        season_ids_to_update = new_df['SEASON_ID'].unique()
        existing_df = existing_df[~existing_df['SEASON_ID'].isin(season_ids_to_update)]
        
        # Combiner
        combined_df = pd.concat([existing_df, new_df], ignore_index=True)
        print(f"✓ {len(new_df):,} nouvelles entrées ajoutées")
    else:
        combined_df = new_df
    
    # Trier par date
    combined_df = combined_df.sort_values('GAME_DATE')
    
    # Supprimer les doublons
    before_dedup = len(combined_df)
    combined_df = combined_df.drop_duplicates(subset=['GAME_ID', 'TEAM_ID'], keep='last')
    after_dedup = len(combined_df)
    
    if before_dedup != after_dedup:
        print(f"🧹 {before_dedup - after_dedup} doublons supprimés")
    
    # Statistiques
    print("\n" + "=" * 70)
    print("RÉSUMÉ")
    print("=" * 70)
    print(f"Total d'entrées:        {len(combined_df):,}")
    print(f"Matchs uniques:         {combined_df['GAME_ID'].nunique():,}")
    print(f"Équipes:                {combined_df['TEAM_ID'].nunique()}")
    print(f"Période:                {combined_df['GAME_DATE'].min().date()} → {combined_df['GAME_DATE'].max().date()}")
    print(f"Colonnes:               {len(combined_df.columns)}")
    
    return combined_df


def save_dataset(df, output_path='data/NBA_GAMES.csv'):
    """Sauvegarde le dataset"""
    
    # Créer une sauvegarde de l'ancien fichier si il existe
    import os
    if os.path.exists(output_path):
        backup_path = f'data/NBA_GAMES_OLD_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        print(f"\n💾 Sauvegarde ancien fichier: {backup_path}")
        os.rename(output_path, backup_path)
    
    # Sauvegarder le nouveau dataset
    df.to_csv(output_path, index=False)
    print(f"💾 Nouveau dataset sauvegardé: {output_path}")
    
    # Afficher la taille du fichier
    file_size = os.path.getsize(output_path) / (1024 * 1024)  # MB
    print(f"📦 Taille du fichier: {file_size:.2f} MB")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Récupérer les matchs NBA')
    parser.add_argument('--full', action='store_true', 
                       help='Téléchargement complet (par défaut: incrémental)')
    
    args = parser.parse_args()
    
    print()
    df = fetch_all_games(incremental=not args.full)
    
    if df is not None:
        save_dataset(df)
        print("\n" + "=" * 70)
        print("✅ TERMINÉ AVEC SUCCÈS")
        print("=" * 70)
        print()
    else:
        print("\n" + "=" * 70)
        print("❌ ÉCHEC")
        print("=" * 70)
        print()
        sys.exit(1)
