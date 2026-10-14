"""
Data Loader - Chargement simple des datasets NBA
"""
import sys
import pandas as pd
from pathlib import Path
from typing import Optional


# Mapping des abréviations historiques vers les abréviations actuelles
TEAM_ABBREVIATION_MAPPING = {
    'CHH': 'CHA',  # Charlotte Hornets (ancien) → Charlotte Hornets (actuel)
    'NJN': 'BKN',  # New Jersey Nets → Brooklyn Nets
    'NOH': 'NOP',  # New Orleans Hornets → New Orleans Pelicans
    'NOK': 'NOP',  # New Orleans/Oklahoma City Hornets → New Orleans Pelicans
    'SEA': 'OKC',  # Seattle SuperSonics → Oklahoma City Thunder
    'VAN': 'MEM',  # Vancouver Grizzlies → Memphis Grizzlies
}


def normalize_team_abbreviation(abbrev: str) -> str:
    """
    Normalise une abréviation d'équipe historique vers l'abréviation actuelle
    
    Args:
        abbrev: Abréviation d'équipe (ex: 'CHH', 'CHA', 'LAL')
        
    Returns:
        Abréviation normalisée (ex: 'CHA', 'CHA', 'LAL')
    """
    return TEAM_ABBREVIATION_MAPPING.get(abbrev, abbrev)


def _dedupe_games(df: pd.DataFrame, label: str) -> pd.DataFrame:
    """
    Une ligne par (match, équipe). Jamais deux.

    Pourquoi c'est ici et pas à l'appel : la déduplication existait côté
    entraînement (`features/engineer.py`) et **pas** côté prédiction. Le
    dataset de la saison 2025-26 est arrivé avec 1 780 lignes dupliquées sur
    4 240 — chaque match compté deux fois. Conséquences mesurées :

    - `SEASON_AVG_TOTAL` valait **398 points en production contre 231 à
      l'entraînement**, parce que la somme par `GAME_ID` additionnait les
      lignes en double. C'est une des 97 features du modèle de victoire.
    - les moyennes glissantes « sur les 5 derniers matchs » ne portaient que
      sur deux ou trois matchs réels, chacun compté deux fois.

    Le modèle décidait donc sur des valeurs que l'entraînement ne lui avait
    jamais montrées, sans qu'aucun test ne rougisse. C'est la troisième fois
    que ce projet rencontre cette forme de défaut ; la réponse est la même que
    les deux précédentes — faire porter la garantie par le chemin commun, pas
    par chaque appelant.

    La duplication amont reste à corriger (`update_data.py` et le dataset
    Kaggle). Ce filet ne la masque pas : il la signale sur stderr.
    """
    keys = [c for c in ('GAME_ID', 'TEAM_ID') if c in df.columns]
    if len(keys) < 2:
        return df
    before = len(df)
    df = df.drop_duplicates(subset=keys)
    removed = before - len(df)
    if removed:
        print(f"  ⚠️  {label} : {removed} ligne(s) dupliquée(s) sur {before} "
              f"écartée(s) — une seule ligne par (match, équipe).",
              file=sys.stderr)
    return df


class NBADataLoader:
    """Charge les datasets NBA depuis les fichiers CSV"""
    
    def __init__(self, data_dir: str = "data"):
        """
        Args:
            data_dir: Répertoire contenant les fichiers CSV
        """
        self.data_dir = Path(data_dir)
    
    def load_games(self, parse_dates: bool = True, normalize_teams: bool = True) -> pd.DataFrame:
        """
        Charge le dataset des matchs NBA
        
        Args:
            parse_dates: Si True, convertit GAME_DATE en datetime
            normalize_teams: Si True, normalise les abréviations historiques (CHH→CHA, etc.)
            
        Returns:
            DataFrame avec tous les matchs
        """
        df = pd.read_csv(self.data_dir / "NBA_GAMES.csv")
        df = _dedupe_games(df, "NBA_GAMES.csv")

        if parse_dates and 'GAME_DATE' in df.columns:
            df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
        
        # Normaliser les abréviations d'équipes historiques
        if normalize_teams and 'TEAM_ABBREVIATION' in df.columns:
            df['TEAM_ABBREVIATION'] = df['TEAM_ABBREVIATION'].apply(normalize_team_abbreviation)
        
        return df
    
    def load_teams(self) -> pd.DataFrame:
        """
        Charge le dataset des équipes NBA
        
        Returns:
            DataFrame avec toutes les équipes
        """
        return pd.read_csv(self.data_dir / "NBA_TEAMS.csv")
    
    def load_players(self, active_only: bool = False) -> pd.DataFrame:
        """
        Charge le dataset des joueurs NBA
        
        Args:
            active_only: Si True, charge uniquement les joueurs actifs
            
        Returns:
            DataFrame avec les joueurs
        """
        if active_only:
            return pd.read_csv(self.data_dir / "NBA_ACTIVE_PLAYERS.csv")
        return pd.read_csv(self.data_dir / "NBA_PLAYERS.csv")
    
    def load_player_games(self, parse_dates: bool = True, normalize_teams: bool = True) -> pd.DataFrame:
        """
        Charge le dataset des stats joueurs par match
        
        Args:
            parse_dates: Si True, convertit GAME_DATE en datetime
            normalize_teams: Si True, normalise les abréviations dans MATCHUP
            
        Returns:
            DataFrame avec les stats des joueurs par match
        """
        df = pd.read_csv(self.data_dir / "NBA_PLAYER_GAMES.csv")
        
        if parse_dates and 'GAME_DATE' in df.columns:
            df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
        
        # Normaliser les abréviations dans le champ MATCHUP (ex: "LAL vs. CHH" → "LAL vs. CHA")
        if normalize_teams and 'MATCHUP' in df.columns:
            for old_abbrev, new_abbrev in TEAM_ABBREVIATION_MAPPING.items():
                df['MATCHUP'] = df['MATCHUP'].str.replace(
                    f' {old_abbrev}', f' {new_abbrev}', regex=False
                )
        
        return df
    
    def get_games_by_season(self, season_id: int) -> pd.DataFrame:
        """
        Récupère les matchs d'une saison spécifique
        
        Args:
            season_id: ID de la saison (ex: 22024 pour 2024-25)
            
        Returns:
            DataFrame filtré sur la saison
        """
        df = self.load_games()
        return df[df['SEASON_ID'] == season_id]
    
    def get_games_by_team(self, team_id: int) -> pd.DataFrame:
        """
        Récupère tous les matchs d'une équipe
        
        Args:
            team_id: ID de l'équipe
            
        Returns:
            DataFrame filtré sur l'équipe
        """
        df = self.load_games()
        return df[df['TEAM_ID'] == team_id]
    
    def get_games_between_dates(
        self, 
        start_date: str, 
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Récupère les matchs entre deux dates
        
        Args:
            start_date: Date de début (format: 'YYYY-MM-DD')
            end_date: Date de fin (format: 'YYYY-MM-DD'), optionnel
            
        Returns:
            DataFrame filtré sur la période
        """
        df = self.load_games()
        df = df[df['GAME_DATE'] >= start_date]
        
        if end_date:
            df = df[df['GAME_DATE'] <= end_date]
        
        return df


if __name__ == "__main__":
    # Test rapide
    loader = NBADataLoader()
    
    print("Test du DataLoader")
    print("=" * 50)
    
    # Charger les matchs
    games = loader.load_games()
    print(f"✓ Matchs chargés: {len(games):,} entrées")
    print(f"  Période: {games['GAME_DATE'].min()} → {games['GAME_DATE'].max()}")
    
    # Charger les équipes
    teams = loader.load_teams()
    print(f"✓ Équipes chargées: {len(teams)} équipes")
    
    # Charger les joueurs
    players = loader.load_players()
    print(f"✓ Joueurs chargés: {len(players):,} joueurs")
    
    active_players = loader.load_players(active_only=True)
    print(f"✓ Joueurs actifs: {len(active_players)} joueurs")
    
    print("\n✅ DataLoader fonctionne correctement!")
