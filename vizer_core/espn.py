"""
espn.py — Accès partagé au scoreboard public d'ESPN.

Une seule API pour les deux sports, sans clé ni quota déclaré :

    https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard?dates=YYYYMMDD
    https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=YYYYMMDD

Deux consommateurs, et c'est la raison d'être de ce module :

- `scripts/publish_results.py` y lit les **scores finaux**, pour clôturer les
  paris et alimenter la mesure de performance ;
- `vizer_nba` y lit le **calendrier à venir**, en recours quand cdn.nba.com
  refuse la requête.

La table d'alias est la vraie raison de ce regroupement. Elle nous a déjà
coûté un défaut silencieux — ESPN abrège l'Utah `UTAH` sur un endpoint et
`UTA` sur un autre, et les paris sur l'Utah ne se clôturaient jamais. Une
table à deux endroits, c'est deux endroits où le prochain écart ne sera
corrigé qu'une fois sur deux.

Pourquoi ESPN et pas les API officielles
----------------------------------------
`cdn.nba.com` et `stats.nba.com` répondent **403 depuis une IP de
datacenter**, et aussi depuis certaines IP résidentielles hors Amérique du
Nord — mesuré, pas supposé. ESPN répond dans les deux cas. L'API officielle
reste la source primaire quand elle est joignable : elle porte les horaires
et les statuts officiels.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import date
from typing import Any

SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard?dates={day}"

SPORT_PATHS = {"nhl": "hockey/nhl", "nba": "basketball/nba"}

# ESPN abrège quelques équipes autrement que le reste du projet. Le reste des
# codes coïncide, on ne remappe donc que les écarts réels.
#
# UTAH → ARI côté NHL n'est pas une coquille : les modèles sont entraînés sur
# l'historique Moneypuck, où la franchise de l'Utah prolonge celle de l'Arizona
# (cf. TEAM_REMAP dans vizer_nhl/src/utils.py). Publier UTA ici casserait
# l'appariement avec les prédictions.
#
# Côté NBA, les six écarts ont été vérifiés contre `NBA_TEAMS.csv` sur les
# deux semaines d'ouverture de la saison 2026-27 : 208 participations, 30
# codes distincts, aucun non résolu.
ALIASES: dict[str, dict[str, str]] = {
    # `UTA` **et** `UTAH` : ESPN n'abrège pas l'Utah pareil selon l'endpoint —
    # `UTAH` sur la liste des équipes, `UTA` sur le scoreboard. Sans les deux,
    # un match de l'Utah est publié sous un code que les prédictions
    # n'emploient jamais, et le pari correspondant ne se clôture pas.
    "nhl": {"LA": "LAK", "NJ": "NJD", "SJ": "SJS", "TB": "TBL",
            "UTAH": "ARI", "UTA": "ARI"},
    "nba": {"GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS",
            "UTAH": "UTA", "WSH": "WAS"},
}


def team_code(sport: str, abbrev: str) -> str:
    """Code ESPN → code du projet."""
    return ALIASES.get(sport, {}).get(abbrev, abbrev)


def fetch(url: str, timeout: int = 30) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "vizer/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def scoreboard(sport: str, day: date, timeout: int = 30) -> dict[str, Any]:
    """Scoreboard brut d'un sport pour une date.

    Attention au fuseau : le paramètre `dates` d'ESPN est une **journée
    américaine**, pas une journée UTC. Un match de 20 h à l'Est apparaît sous
    sa date locale alors que son horodatage UTC est le lendemain. Les deux
    passages quotidiens du job (07 h et 20 h UTC) tombent tous deux sur la même
    journée américaine que la journée UTC courante, donc l'écart ne se
    manifeste pas — mais il se manifesterait pour un passage entre 00 h et
    05 h UTC.
    """
    url = SCOREBOARD.format(path=SPORT_PATHS[sport], day=day.strftime("%Y%m%d"))
    return fetch(url, timeout=timeout)


def upcoming(sport: str, day: date, timeout: int = 30) -> list[dict[str, Any]]:
    """
    Matchs **non encore commencés** d'une journée américaine.

    Returns:
        Liste de dicts `{home, away, commence_time, status, event_id}`, codes
        déjà traduits vers ceux du projet. Un match en cours ou terminé est
        écarté : prédire un match commencé n'a pas de sens, et le feed sert à
        décider avant le coup d'envoi.
    """
    out: list[dict[str, Any]] = []
    for event in scoreboard(sport, day, timeout=timeout).get("events") or []:
        comps = event.get("competitions") or []
        if not comps:
            continue
        comp = comps[0]
        state = ((comp.get("status") or {}).get("type") or {}).get("state")
        if state != "pre":
            continue
        sides = {c.get("homeAway"): c for c in comp.get("competitors") or []}
        home, away = sides.get("home"), sides.get("away")
        if not home or not away:
            continue
        try:
            home_code = team_code(sport, home["team"]["abbreviation"])
            away_code = team_code(sport, away["team"]["abbreviation"])
        except (KeyError, TypeError):
            continue
        out.append({
            "home": home_code,
            "away": away_code,
            "commence_time": event.get("date"),
            "status": "scheduled",
            "event_id": str(event.get("id") or ""),
        })
    return out
