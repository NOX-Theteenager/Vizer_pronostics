"""
nba_schedule.py — Détection des matchs NBA via l'API CDN officielle.

Source primaire de détection des matchs (avant de se rabattre sur Odds API).
Utilise les endpoints publics cdn.nba.com (pas de clé requise) :
  - todaysScoreboard_00.json : matchs du jour
  - scheduleLeagueV2.json    : calendrier complet de la saison

Retourne une liste de ScheduledGame (home/away en codes 3 lettres).
Les cotes restent fournies par Odds API ; ce module ne sert qu'à DÉTECTER
les matchs (équipes + horaires officiels).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import requests


# Endpoints CDN publics NBA (pas de clé API nécessaire)
TODAYS_SCOREBOARD_URL = "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"
SCHEDULE_URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"

# Tricodes NBA officiels → on les garde tels quels (déjà 3 lettres standard)
# Quelques alias historiques pour robustesse
NBA_TRICODE_REMAP: dict[str, str] = {
    'NOP': 'NOP', 'NOH': 'NOP',   # New Orleans
    'PHX': 'PHX', 'PHO': 'PHX',   # Phoenix
    'BKN': 'BKN', 'BRK': 'BKN',   # Brooklyn
    'CHA': 'CHA', 'CHO': 'CHA',   # Charlotte
}


@dataclass
class ScheduledGame:
    """Un match NBA détecté via l'API officielle."""
    home: str          # tricode 3 lettres
    away: str
    game_time_utc: str
    game_id: str = ""
    status: str = ""   # 'scheduled', 'live', 'final'


class NBAScheduleError(Exception):
    pass


class NBAScheduleClient:
    """
    Client de détection des matchs NBA via l'API CDN officielle.

    Usage :
        client = NBAScheduleClient()
        games = client.get_today_games()       # matchs du jour
        games = client.get_games_for_date('2026-05-21')   # date précise
    """

    def __init__(self, timeout: int = 12):
        self.timeout = timeout

    def _normalize(self, tricode: str) -> str:
        return NBA_TRICODE_REMAP.get(tricode, tricode)

    def _fetch_json(self, url: str) -> dict:
        last_exc = None
        for attempt in range(3):
            try:
                r = requests.get(url, timeout=self.timeout,
                                 headers={'User-Agent': 'Mozilla/5.0'})
                if r.status_code != 200:
                    raise NBAScheduleError(f"HTTP {r.status_code} sur {url}")
                return r.json()
            except requests.RequestException as e:
                last_exc = e
                if attempt < 2:
                    import time as _t
                    _t.sleep(2 ** attempt)
        raise NBAScheduleError(f"Échec réseau NBA API (3 tentatives) : {last_exc}")

    def get_today_games(self) -> list[ScheduledGame]:
        """
        Récupère les matchs du jour via todaysScoreboard.

        Returns:
            Liste de ScheduledGame. Peut être vide (jour sans match).
        Raises:
            NBAScheduleError si l'API est injoignable.
        """
        data = self._fetch_json(TODAYS_SCOREBOARD_URL)
        scoreboard = data.get("scoreboard", {})
        games = []
        status_map = {1: "scheduled", 2: "live", 3: "final"}
        for g in scoreboard.get("games", []):
            home = g.get("homeTeam", {}).get("teamTricode", "")
            away = g.get("awayTeam", {}).get("teamTricode", "")
            if not home or not away:
                continue
            games.append(ScheduledGame(
                home=self._normalize(home),
                away=self._normalize(away),
                game_time_utc=g.get("gameTimeUTC", ""),
                game_id=str(g.get("gameId", "")),
                status=status_map.get(g.get("gameStatus", 1), "scheduled"),
            ))
        return games

    def get_games_for_date(self, date_str: str) -> list[ScheduledGame]:
        """
        Récupère les matchs d'une date précise (format 'YYYY-MM-DD') via le
        calendrier complet de la saison.
        """
        data = self._fetch_json(SCHEDULE_URL)
        target = datetime.strptime(date_str, "%Y-%m-%d").date()
        games = []
        league = data.get("leagueSchedule", {})
        for game_date in league.get("gameDates", []):
            # gameDate au format "MM/DD/YYYY HH:MM:SS"
            raw = game_date.get("gameDate", "")
            try:
                d = datetime.strptime(raw.split(" ")[0], "%m/%d/%Y").date()
            except ValueError:
                continue
            if d != target:
                continue
            for g in game_date.get("games", []):
                home = g.get("homeTeam", {}).get("teamTricode", "")
                away = g.get("awayTeam", {}).get("teamTricode", "")
                if not home or not away:
                    continue
                games.append(ScheduledGame(
                    home=self._normalize(home),
                    away=self._normalize(away),
                    game_time_utc=g.get("gameDateTimeUTC", ""),
                    game_id=str(g.get("gameId", "")),
                    status="scheduled",
                ))
        return games

    def get_upcoming_games(self, days_ahead: int = 1) -> list[ScheduledGame]:
        """
        Matchs d'aujourd'hui + N jours suivants (via le calendrier complet).
        Utile pour anticiper les matchs de demain.
        """
        from datetime import timedelta
        today = datetime.now(timezone.utc).date()
        all_games = []
        try:
            data = self._fetch_json(SCHEDULE_URL)
        except NBAScheduleError:
            # fallback : juste aujourd'hui
            return self.get_today_games()

        league = data.get("leagueSchedule", {})
        target_dates = {today + timedelta(days=i) for i in range(days_ahead + 1)}
        for game_date in league.get("gameDates", []):
            raw = game_date.get("gameDate", "")
            try:
                d = datetime.strptime(raw.split(" ")[0], "%m/%d/%Y").date()
            except ValueError:
                continue
            if d not in target_dates:
                continue
            for g in game_date.get("games", []):
                home = g.get("homeTeam", {}).get("teamTricode", "")
                away = g.get("awayTeam", {}).get("teamTricode", "")
                if not home or not away:
                    continue
                all_games.append(ScheduledGame(
                    home=self._normalize(home),
                    away=self._normalize(away),
                    game_time_utc=g.get("gameDateTimeUTC", ""),
                    game_id=str(g.get("gameId", "")),
                    status="scheduled",
                ))
        return all_games
