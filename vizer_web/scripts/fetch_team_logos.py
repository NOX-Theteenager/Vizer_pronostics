#!/usr/bin/env python3
"""
Télécharge les logos d'équipes une fois pour toutes, dans `public/logos/`.

Pourquoi les héberger et non les pointer
----------------------------------------
Les référencer directement sur le CDN d'ESPN ajouterait une origine tierce à
chaque écran : requêtes non maîtrisées, rien en cache hors-ligne, et un tiers
qui voit passer la navigation de chaque utilisateur. Toute l'architecture de
l'app consiste à l'éviter. On les récupère donc une fois, on les réduit, et le
service worker les met en cache comme n'importe quelle ressource de l'app.

Droits
------
Ces logos sont des marques déposées des franchises. Les héberger dans une
application publique relève de la décision du propriétaire du projet, pas de
ce script. Le repli monogramme reste en place : si un fichier manque, l'app
affiche la pastille colorée qu'elle utilisait avant, rien ne casse.

Sortie : public/logos/<sport>/<CODE>.png — 80 px, transparent.

Usage : python3 scripts/fetch_team_logos.py
"""
from __future__ import annotations

import io
import json
import pathlib
import sys
import urllib.error
import urllib.request

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / 'public' / 'logos'

TEAMS_API = 'https://site.api.espn.com/apis/site/v2/sports/{path}/teams?limit=50'
LEAGUES = {'nhl': 'hockey/nhl', 'nba': 'basketball/nba'}

# Mêmes correspondances que `scripts/publish_results.py` et `api/live.ts` :
# ESPN abrège quelques équipes autrement que le reste du projet.
#
# UTAH → ARI n'est pas une coquille. Les modèles sont entraînés sur un
# historique où la franchise de l'Utah prolonge celle de l'Arizona, et les
# prédictions publient donc ARI. Le fichier porte le logo actuel de la
# franchise, sous le code que l'app recevra.
ALIASES = {
    'nhl': {'LA': 'LAK', 'NJ': 'NJD', 'SJ': 'SJS', 'TB': 'TBL',
            'UTAH': 'ARI', 'UTA': 'ARI'},
    'nba': {'GS': 'GSW', 'NO': 'NOP', 'NY': 'NYK', 'SA': 'SAS',
            'UTAH': 'UTA', 'WSH': 'WAS'},
}

SIZE = 80  # affiché entre 26 et 44 px : 80 couvre les écrans à forte densité


def get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={'User-Agent': 'vizer-logos/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def default_logo(team: dict) -> str | None:
    """L'URL du logo plein, celle marquée `default` par ESPN."""
    logos = team.get('logos') or []
    for logo in logos:
        if 'default' in (logo.get('rel') or []):
            return logo.get('href')
    return logos[0].get('href') if logos else None


def shrink(data: bytes) -> bytes:
    """Réduit à SIZE px de côté, fond transparent conservé."""
    im = Image.open(io.BytesIO(data)).convert('RGBA')
    im.thumbnail((SIZE, SIZE), Image.LANCZOS)
    # Carré centré : l'app peut poser une taille fixe sans déformer.
    canvas = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    canvas.paste(im, ((SIZE - im.width) // 2, (SIZE - im.height) // 2), im)
    buf = io.BytesIO()
    canvas.save(buf, 'PNG', optimize=True)
    return buf.getvalue()


def main() -> int:
    total = 0
    written = 0

    for sport, path in LEAGUES.items():
        folder = OUT / sport
        folder.mkdir(parents=True, exist_ok=True)
        try:
            payload = json.loads(get(TEAMS_API.format(path=path)))
            teams = payload['sports'][0]['leagues'][0]['teams']
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError, IndexError) as e:
            print(f"❌ {sport.upper()} : liste des équipes indisponible ({e})", file=sys.stderr)
            continue

        print(f"\n─── {sport.upper()} ─── {len(teams)} équipes")
        for entry in teams:
            team = entry.get('team') or {}
            abbrev = team.get('abbreviation')
            url = default_logo(team)
            if not abbrev or not url:
                print(f"  ⚠️  {abbrev or '???'} : pas de logo publié")
                continue

            code = ALIASES[sport].get(abbrev, abbrev)
            try:
                png = shrink(get(url))
            except Exception as e:  # réseau, format, décodage
                print(f"  ⚠️  {code} : {type(e).__name__}: {e}")
                continue

            (folder / f'{code}.png').write_bytes(png)
            total += len(png)
            written += 1
            print(f"  ✓ {code:4s} {len(png) // 1024:>3d} ko  ({team.get('displayName')})")

    print(f"\n✅ {written} logos · {total // 1024} ko au total → {OUT}")
    return 0 if written else 1


if __name__ == '__main__':
    raise SystemExit(main())
