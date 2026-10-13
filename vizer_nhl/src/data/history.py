"""
history.py — Forme récente et confrontations directes NHL.

**Source : `all_teams.csv`, lignes `situation == 'all'`.** Le dataset agrégé
utilisé pour les features ne contient que du 5-contre-5 : s'en servir pour les
résultats produirait des scores faux (un 3-2 réel peut y apparaître 0-0). Les
lignes `all` de Moneypuck donnent, elles, le score final.

Une ligne par équipe et par match : on garde celles marquées `HOME` pour
reconstituer le match complet.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from ..utils import normalize_team_code

USECOLS = ['team', 'opposingTeam', 'gameDate', 'situation',
           'home_or_away', 'goalsFor', 'goalsAgainst']


def _parse_date(value: Any) -> Optional[str]:
    """`20240114` ou `2024-01-14` → `2024-01-14`."""
    s = str(value).strip()
    if not s or s.lower() == 'nan':
        return None
    if len(s) == 8 and s.isdigit():
        return f'{s[:4]}-{s[4:6]}-{s[6:]}'
    return s[:10]


class NHLMatchHistory:
    """Index compact des matchs passés (scores finaux)."""

    EMPTY = ['date', 'home', 'away', 'home_score', 'away_score']

    def __init__(self, games: Optional[pd.DataFrame] = None):
        self.games = games if games is not None else pd.DataFrame(columns=self.EMPTY)

    # ------------------------------------------------------------------
    @classmethod
    def from_data_dir(cls, data_dir: str | Path,
                      filename: str = 'all_teams.csv') -> 'NHLMatchHistory':
        """
        Construit l'historique depuis `all_teams.csv`.

        Si le fichier est absent (environnement partiel), on retourne un
        historique vide : la PWA masque simplement les cartes concernées.
        """
        path = Path(data_dir) / filename
        if not path.exists():
            # Silencieux côté PWA (les cartes disparaissent), mais pas côté
            # logs : c'est exactement comme ça que forme et confrontations
            # sont parties vides en production sans que rien ne le signale.
            print(f"⚠️  Historique indisponible : {path} absent — forme et "
                  f"confrontations directes seront vides.", file=sys.stderr)
            return cls()
        try:
            raw = pd.read_csv(path, usecols=USECOLS)
        except Exception:
            return cls()

        raw = raw[(raw['situation'] == 'all') & (raw['home_or_away'] == 'HOME')]
        if raw.empty:
            return cls()

        out = pd.DataFrame({
            'date': raw['gameDate'].map(_parse_date),
            'home': raw['team'].map(lambda v: normalize_team_code(str(v))),
            'away': raw['opposingTeam'].map(lambda v: normalize_team_code(str(v))),
            'home_score': pd.to_numeric(raw['goalsFor'], errors='coerce'),
            'away_score': pd.to_numeric(raw['goalsAgainst'], errors='coerce'),
        }).dropna()
        out['home_score'] = out['home_score'].astype(int)
        out['away_score'] = out['away_score'].astype(int)
        return cls(out.sort_values('date').reset_index(drop=True))

    # ------------------------------------------------------------------
    def recent_form(self, team: str, n: int = 5) -> Optional[dict[str, Any]]:
        """`n` derniers résultats de `team`, du plus ancien au plus récent."""
        code = normalize_team_code(str(team))
        g = self.games
        if g.empty:
            return None
        played = g[(g['home'] == code) | (g['away'] == code)].tail(n)
        if played.empty:
            return None

        results, gf, ga = [], 0, 0
        for _, row in played.iterrows():
            at_home = row['home'] == code
            scored = int(row['home_score'] if at_home else row['away_score'])
            conceded = int(row['away_score'] if at_home else row['home_score'])
            gf += scored
            ga += conceded
            # La NHL tranche toujours (prolongation / tirs au but) : un nul
            # n'apparaîtrait que sur une donnée incomplète.
            results.append('W' if scored > conceded else 'L' if scored < conceded else 'D')

        return {
            'results': results,
            'wins': results.count('W'),
            'draws': results.count('D'),
            'losses': results.count('L'),
            'goals_for': gf,
            'goals_against': ga,
        }

    # ------------------------------------------------------------------
    def head_to_head(self, home: str, away: str, n: int = 5) -> list[dict[str, Any]]:
        """Dernières confrontations entre les deux équipes, plus récente d'abord."""
        h = normalize_team_code(str(home))
        a = normalize_team_code(str(away))
        g = self.games
        if g.empty:
            return []
        mask = ((g['home'] == h) & (g['away'] == a)) | ((g['home'] == a) & (g['away'] == h))
        rows = g[mask].tail(n).iloc[::-1]

        out: list[dict[str, Any]] = []
        for _, row in rows.iterrows():
            hs, as_ = int(row['home_score']), int(row['away_score'])
            winner = row['home'] if hs > as_ else row['away'] if as_ > hs else None
            out.append({
                'date': row['date'],
                'home': row['home'],
                'away': row['away'],
                'home_score': hs,
                'away_score': as_,
                # Exprimé par rapport au match **à venir**, pour que la PWA
                # n'ait pas à re-raisonner sur qui recevait ce jour-là.
                'winner': None if winner is None else ('home' if winner == h else 'away'),
            })
        return out
