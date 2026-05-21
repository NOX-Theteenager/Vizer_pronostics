"""
downloader.py — Téléchargement incrémental des CSVs Moneypuck (réplique 01).

Télécharge les fichiers de la saison courante depuis Moneypuck et les fusionne
de façon incrémentale (seuls les gameId absents sont ajoutés) avec les CSVs
historiques locaux.

Source : https://peter-tanner.com/moneypuck/downloads/
  - skaters/<saison>.zip
  - lines/<saison>.zip
  - goalies/<saison>.zip
  - all_teams.csv (téléchargé séparément / historique)

Usage :
    from src.data.downloader import MoneypuckDownloader
    dl = MoneypuckDownloader(data_dir='data', season=2025)
    dl.update_current_season()        # skaters/lines/goalies de la saison
    dl.download_shots()               # optionnel (2.5 GB) pour period_stats
"""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path
from typing import Optional

import pandas as pd
import requests


MONEYPUCK_BASE = "https://peter-tanner.com/moneypuck/downloads"


class MoneypuckDownloader:
    """
    Télécharge et met à jour les CSVs Moneypuck de la saison courante.

    Args:
        data_dir : dossier de destination des CSVs
        season   : année de la saison courante (ex: 2025)
        timeout  : timeout HTTP en secondes
    """

    def __init__(self, data_dir: str = 'data', season: Optional[int] = None,
                 timeout: int = 60):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if season is None:
            from ..season import current_nhl_season
            season = current_nhl_season()
        self.season = season
        self.timeout = timeout

    def _files_config(self) -> dict[str, dict]:
        """URLs et chemins des 3 catégories pour la saison courante."""
        return {
            'skaters': {
                'url': f"{MONEYPUCK_BASE}/seasonPlayersSummary/skaters/{self.season}.zip",
                'path': self.data_dir / f"skaters_{self.season}.csv",
            },
            'lines': {
                'url': f"{MONEYPUCK_BASE}/seasonPlayersSummary/lines/{self.season}.zip",
                'path': self.data_dir / f"lines_{self.season}.csv",
            },
            'goalies': {
                'url': f"{MONEYPUCK_BASE}/seasonPlayersSummary/goalies/{self.season}.zip",
                'path': self.data_dir / f"goalies_{self.season}.csv",
            },
        }

    def _download_zip_csv(self, url: str) -> pd.DataFrame:
        """Télécharge un zip et retourne le CSV interne en DataFrame."""
        r = requests.get(url, timeout=self.timeout)
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            csv_name = [f for f in z.namelist() if f.endswith('.csv')][0]
            return pd.read_csv(z.open(csv_name))

    def update_current_season(self) -> dict[str, str]:
        """
        Met à jour skaters/lines/goalies de la saison courante (incrémental).

        Returns:
            dict {catégorie: statut} récapitulatif.
        """
        results = {}
        for cat, info in self._files_config().items():
            path = info['path']
            try:
                df_new = self._download_zip_csv(info['url'])
                if path.exists():
                    existing_ids = set(
                        pd.read_csv(path, usecols=['gameId'])['gameId'].unique()
                    )
                    df_to_add = df_new[~df_new['gameId'].isin(existing_ids)]
                    if not df_to_add.empty:
                        df_to_add.to_csv(path, mode='a', header=False, index=False)
                        results[cat] = f"✅ +{len(df_to_add)} lignes"
                    else:
                        results[cat] = "✓ Déjà à jour"
                else:
                    df_new.to_csv(path, index=False)
                    results[cat] = f"🆕 Créé ({len(df_new)} lignes)"
            except Exception as e:
                results[cat] = f"❌ Erreur : {str(e)[:80]}"
            print(f"  {cat.upper():<10} {results[cat]}", file=sys.stderr)
        return results

    def download_shots(self, historical: bool = False,
                       force: bool = False) -> dict[str, str]:
        """
        Télécharge les fichiers shots (volumineux) pour period_stats.

        Incrémental : seuls les game_id absents du fichier local sont ajoutés.
        Le fichier historique (2007-2024) étant figé, il est sauté s'il existe
        déjà (sauf force=True).

        Args:
            historical : si True, télécharge aussi shots_2007-2024.csv (~2.3 GB).
            force      : si True, re-télécharge tout intégralement (écrase).
        """
        results = {}
        targets = {
            'shots_current': {
                'url': f"{MONEYPUCK_BASE}/shots_{self.season}.zip",
                'path': self.data_dir / f"shots_{self.season}.csv",
                'frozen': False,   # la saison courante évolue
            },
        }
        if historical:
            targets['shots_historical'] = {
                'url': f"{MONEYPUCK_BASE}/shots_2007-2024.zip",
                'path': self.data_dir / "shots_2007-2024.csv",
                'frozen': True,    # historique figé : ne change jamais
            }

        for name, info in targets.items():
            path = info['path']
            try:
                # 1. Fichier figé déjà présent → skip (sauf force)
                if info['frozen'] and path.exists() and not force:
                    results[name] = "✓ Historique déjà présent (figé, skip)"
                    print(f"  {name:<18} {results[name]}", file=sys.stderr)
                    continue

                # 2. Téléchargement
                print(f"  ⬇️  {name} (volumineux, patience)...", file=sys.stderr)
                df_new = self._download_zip_csv(info['url'])

                # Détecter la colonne identifiante (game_id côté shots)
                id_col = 'game_id' if 'game_id' in df_new.columns else (
                    'gameId' if 'gameId' in df_new.columns else None)

                # 3. Incrémental si fichier existe, colonne ID dispo, et pas force
                if path.exists() and id_col and not force:
                    existing_ids = set(
                        pd.read_csv(path, usecols=[id_col])[id_col].unique()
                    )
                    df_to_add = df_new[~df_new[id_col].isin(existing_ids)]
                    if not df_to_add.empty:
                        df_to_add.to_csv(path, mode='a', header=False, index=False)
                        n_games = df_to_add[id_col].nunique()
                        results[name] = f"✅ +{len(df_to_add):,} tirs ({n_games} matchs)"
                    else:
                        results[name] = "✓ Déjà à jour"
                else:
                    # Création initiale (ou force)
                    df_new.to_csv(path, index=False)
                    results[name] = f"🆕 Créé ({len(df_new):,} tirs)"
            except Exception as e:
                results[name] = f"❌ Erreur : {str(e)[:80]}"
            print(f"  {name:<18} {results[name]}", file=sys.stderr)
        return results
