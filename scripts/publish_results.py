#!/usr/bin/env python
"""
publish_results.py — Publie les scores finaux des matchs déjà joués.

Pourquoi ce script
------------------
La PWA sait quels paris l'utilisateur suit, mais pas comment les matchs se
sont terminés : la clôture est restée manuelle depuis le début. Le backend
publiait des prédictions sans jamais publier la réalité, ce qui empêchait
aussi toute mesure de ROI réelle.

Source
------
Le scoreboard public d'ESPN, une seule API pour les deux sports :

    https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard?dates=YYYYMMDD
    https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=YYYYMMDD

Pas de clé, pas de quota déclaré, et — contrairement à cdn.nba.com et à
stats.nba.com — accessible depuis les IP de datacenter, donc depuis un runner
GitHub. Elle donne le score final **et** le détail par période, ce qui permet
de régler les marchés P1/Q1 autant que le moneyline.

Sortie
------
    results/YYYY-MM-DD.json   un fichier par jour
    results/latest.json       fenêtre glissante des N derniers jours

La PWA ne lit que `latest.json` : un seul fetch pour clôturer tout ce qui
traîne. Les fichiers datés servent au backtest et à l'audit.

Usage
-----
    python scripts/publish_results.py --out /tmp/results --days 3
    python scripts/publish_results.py --out /tmp/results --date 2026-10-12
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ESPN = "https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard?dates={day}"

SPORT_PATHS = {"nhl": "hockey/nhl", "nba": "basketball/nba"}

# ESPN abrège quelques équipes autrement que le reste du projet. Le reste des
# codes coïncide, on ne remappe donc que les écarts réels.
#
# UTAH → ARI côté NHL n'est pas une coquille : les modèles sont entraînés sur
# l'historique Moneypuck, où la franchise de l'Utah prolonge celle de l'Arizona
# (cf. TEAM_REMAP dans vizer_nhl/src/utils.py). Publier UTA ici casserait
# l'appariement avec les prédictions.
ALIASES: dict[str, dict[str, str]] = {
    "nhl": {"LA": "LAK", "NJ": "NJD", "SJ": "SJS", "TB": "TBL", "UTAH": "ARI"},
    "nba": {"GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS",
            "UTAH": "UTA", "WSH": "WAS"},
}


def team_code(sport: str, abbrev: str) -> str:
    return ALIASES.get(sport, {}).get(abbrev, abbrev)


def fetch(url: str, timeout: int = 30) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "vizer-results/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _periods(competitors: list[dict]) -> list[dict[str, int]]:
    """Scores par période, alignés domicile/extérieur.

    ESPN ne garantit pas que les deux équipes aient le même nombre de lignes
    (match abandonné, données partielles) : on s'arrête à la plus courte
    plutôt que d'inventer un 0.
    """
    by_side = {}
    for c in competitors:
        by_side[c.get("homeAway")] = [
            int(ls.get("value", 0)) for ls in (c.get("linescores") or [])
        ]
    home, away = by_side.get("home", []), by_side.get("away", [])
    return [{"home": h, "away": a} for h, a in zip(home, away)]


def parse_day(sport: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extrait les matchs **terminés** d'un scoreboard ESPN.

    Un match en cours ou reporté n'est pas publié : une clôture de pari sur un
    score partiel serait pire qu'une clôture manuelle.
    """
    out: list[dict[str, Any]] = []
    for event in payload.get("events", []):
        comps = event.get("competitions") or []
        if not comps:
            continue
        comp = comps[0]
        status = (comp.get("status") or {}).get("type") or {}
        if not status.get("completed"):
            continue

        sides = {c.get("homeAway"): c for c in comp.get("competitors", [])}
        home, away = sides.get("home"), sides.get("away")
        if not home or not away:
            continue
        try:
            home_score = int(home.get("score"))
            away_score = int(away.get("score"))
        except (TypeError, ValueError):
            continue

        periods = _periods(comp.get("competitors", []))
        out.append({
            "sport": sport,
            "home": team_code(sport, home["team"]["abbreviation"]),
            "away": team_code(sport, away["team"]["abbreviation"]),
            "home_name": home["team"].get("displayName"),
            "away_name": away["team"].get("displayName"),
            "commence_time": event.get("date"),
            "home_score": home_score,
            "away_score": away_score,
            # Prolongation ou tirs au but : le marché « vainqueur » se règle sur
            # le score final, mais un total de buts ne compte pas pareil selon
            # les books. On publie le fait, la PWA décide.
            "overtime": len(periods) > (3 if sport == "nhl" else 4),
            "periods": periods,
            "winner": "home" if home_score > away_score
                      else "away" if away_score > home_score else "draw",
            "status": "final",
        })
    return out


def collect(days: list[date], sports: list[str]) -> dict[str, list[dict]]:
    """Récupère jour par jour. Un sport ou un jour en échec n'arrête rien."""
    by_day: dict[str, list[dict]] = {}
    for day in days:
        key = day.isoformat()
        games: list[dict] = []
        for sport in sports:
            url = ESPN.format(path=SPORT_PATHS[sport], day=day.strftime("%Y%m%d"))
            try:
                games.extend(parse_day(sport, fetch(url)))
            except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as e:
                print(f"  ⚠️  {sport.upper()} {key} : {type(e).__name__}: {e}",
                      file=sys.stderr)
        by_day[key] = games
        print(f"  ✓ {key} — {len(games)} match(s) terminé(s)", file=sys.stderr)
    return by_day


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Publie les scores finaux (ESPN).")
    ap.add_argument("--out", required=True, help="Dossier de sortie")
    ap.add_argument("--days", type=int, default=3,
                    help="Nombre de jours à remonter depuis hier (défaut 3)")
    ap.add_argument("--date", default=None,
                    help="Jour unique YYYY-MM-DD (ignore --days)")
    ap.add_argument("--window", type=int, default=7,
                    help="Jours agrégés dans latest.json (défaut 7)")
    ap.add_argument("--sports", nargs="*", default=["nhl", "nba"])
    args = ap.parse_args(argv)

    today = datetime.now(timezone.utc).date()
    if args.date:
        days = [date.fromisoformat(args.date)]
    else:
        # On part d'aujourd'hui : un match commencé à 17h UTC est fini bien
        # avant minuit, et le job tourne le lendemain matin.
        days = [today - timedelta(days=i) for i in range(args.days)]

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    by_day = collect(days, args.sports)
    for key, games in by_day.items():
        if not games:
            # Jour sans match terminé : pas de fichier vide qui écraserait un
            # fichier correct publié plus tôt.
            continue
        (out_dir / f"{key}.json").write_text(
            json.dumps({"date": key, "generated_at": now, "games": games},
                       ensure_ascii=False, indent=2), encoding="utf-8")

    # latest.json : fenêtre glissante, un seul fetch pour la PWA.
    window_days = [today - timedelta(days=i) for i in range(args.window)]
    merged: list[dict] = []
    for day in window_days:
        key = day.isoformat()
        if key in by_day:
            merged.extend(by_day[key])
        else:
            # Jour hors du scan de ce run : on reprend le fichier publié.
            f = out_dir / f"{key}.json"
            if f.exists():
                try:
                    merged.extend(json.loads(f.read_text())["games"])
                except (ValueError, KeyError):
                    pass

    (out_dir / "latest.json").write_text(
        json.dumps({
            "generated_at": now,
            "window_days": args.window,
            "from": window_days[-1].isoformat(),
            "to": window_days[0].isoformat(),
            "n_games": len(merged),
            "games": merged,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✅ {len(merged)} résultat(s) dans latest.json "
          f"({window_days[-1]} → {window_days[0]})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
