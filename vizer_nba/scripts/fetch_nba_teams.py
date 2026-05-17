"""
Script pour récupérer la liste complète des équipes NBA
"""
import pandas as pd
from nba_api.stats.static import teams
from datetime import datetime
import os

def fetch_teams():
    """Récupère toutes les équipes NBA"""
    
    print("=" * 70)
    print("RÉCUPÉRATION DES ÉQUIPES NBA")
    print("=" * 70)
    print()
    
    # Récupérer toutes les équipes
    print("📥 Récupération des équipes...", end=" ", flush=True)
    nba_teams = teams.get_teams()
    print(f"✓ {len(nba_teams)} équipes")
    
    # Convertir en DataFrame
    df = pd.DataFrame(nba_teams)
    
    # Afficher les informations
    print("\n" + "=" * 70)
    print("RÉSUMÉ")
    print("=" * 70)
    print(f"Nombre d'équipes:       {len(df)}")
    print(f"Colonnes:               {len(df.columns)}")
    
    print("\nColonnes disponibles:")
    for i, col in enumerate(df.columns, 1):
        print(f"  {i}. {col}")
    
    print("\nAperçu des équipes:")
    for _, team in df.head(5).iterrows():
        print(f"  • {team['full_name']} ({team['abbreviation']}) - ID: {team['id']}")
    print(f"  ... et {len(df) - 5} autres")
    
    return df


def save_dataset(df, output_path='data/NBA_TEAMS.csv'):
    """Sauvegarde le dataset"""
    
    # Créer une sauvegarde de l'ancien fichier si il existe
    if os.path.exists(output_path):
        backup_path = f'data/NBA_TEAMS_OLD_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
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
    df = fetch_teams()
    
    if df is not None and not df.empty:
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
