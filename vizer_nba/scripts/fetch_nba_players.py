"""
Script pour récupérer la liste complète des joueurs NBA (tous + actifs)
"""
import pandas as pd
from nba_api.stats.static import players
from datetime import datetime
import os

def fetch_all_players():
    """Récupère tous les joueurs NBA (historique complet)"""
    
    print("=" * 70)
    print("RÉCUPÉRATION DES JOUEURS NBA")
    print("=" * 70)
    print()
    
    # Récupérer tous les joueurs
    print("📥 Récupération de tous les joueurs...", end=" ", flush=True)
    all_players = players.get_players()
    print(f"✓ {len(all_players)} joueurs")
    
    # Convertir en DataFrame
    df = pd.DataFrame(all_players)
    
    # Statistiques
    active_count = df['is_active'].sum() if 'is_active' in df.columns else 0
    inactive_count = len(df) - active_count
    
    print("\n" + "=" * 70)
    print("RÉSUMÉ - TOUS LES JOUEURS")
    print("=" * 70)
    print(f"Total de joueurs:       {len(df):,}")
    print(f"Joueurs actifs:         {active_count:,}")
    print(f"Joueurs inactifs:       {inactive_count:,}")
    print(f"Colonnes:               {len(df.columns)}")
    
    print("\nColonnes disponibles:")
    for i, col in enumerate(df.columns, 1):
        print(f"  {i}. {col}")
    
    return df


def fetch_active_players():
    """Récupère uniquement les joueurs actifs"""
    
    print("\n" + "=" * 70)
    print("FILTRAGE DES JOUEURS ACTIFS")
    print("=" * 70)
    print()
    
    # Récupérer les joueurs actifs
    print("📥 Récupération des joueurs actifs...", end=" ", flush=True)
    active_players = players.get_active_players()
    print(f"✓ {len(active_players)} joueurs actifs")
    
    # Convertir en DataFrame
    df = pd.DataFrame(active_players)
    
    print("\nAperçu des joueurs actifs:")
    for _, player in df.head(5).iterrows():
        print(f"  • {player['full_name']} - ID: {player['id']}")
    print(f"  ... et {len(df) - 5} autres")
    
    return df


def save_dataset(df, output_path):
    """Sauvegarde le dataset"""
    
    # Créer une sauvegarde de l'ancien fichier si il existe
    if os.path.exists(output_path):
        backup_path = output_path.replace('.csv', f'_OLD_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')
        print(f"\n💾 Sauvegarde ancien fichier: {backup_path}")
        os.rename(output_path, backup_path)
    
    # Sauvegarder le nouveau dataset
    df.to_csv(output_path, index=False)
    print(f"💾 Nouveau dataset sauvegardé: {output_path}")
    
    # Afficher la taille du fichier
    file_size = os.path.getsize(output_path) / 1024  # KB
    print(f"📦 Taille du fichier: {file_size:.2f} KB")


if __name__ == "__main__":
    print()
    
    # Récupérer tous les joueurs
    all_players_df = fetch_all_players()
    
    if all_players_df is not None and not all_players_df.empty:
        save_dataset(all_players_df, 'data/NBA_PLAYERS.csv')
    
    # Récupérer les joueurs actifs
    active_players_df = fetch_active_players()
    
    if active_players_df is not None and not active_players_df.empty:
        save_dataset(active_players_df, 'data/NBA_ACTIVE_PLAYERS.csv')
    
    print("\n" + "=" * 70)
    print("✅ TERMINÉ AVEC SUCCÈS")
    print("=" * 70)
    print()
