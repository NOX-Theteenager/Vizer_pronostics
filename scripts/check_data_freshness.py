#!/usr/bin/env python
"""
check_data_freshness.py — Les données d'entraînement suivent-elles la saison ?

Pourquoi ce contrôle existe
---------------------------
Les deux fournisseurs bloquent les IP de datacenter, donc les datasets sont
préparés par un PC à IP résidentielle et publiés sur Kaggle par un cron du
dimanche soir. Le crontab le dit lui-même : « un cron ne rattrape pas une
exécution manquée : PC éteint le dimanche soir = rien ne se passe, et rien ne
prévient. »

C'est exactement ce qui est arrivé. Mesuré le 26/10/2026 :

- NHL : dataset arrêté au **13 octobre**, treize jours de retard ;
- NBA : dataset arrêté au **27 mai**, soit aucun match de la saison en cours.

Conséquence, mesurée elle aussi : la NHL est passée de 6,10 à 6,43 buts par
match après le 13 octobre, et le modèle de 5,73 à 5,75 buts attendus. Il ne
pouvait pas suivre. Le marché `total` est passé de +11,6 % à **−22,0 %**, et
le biais de niveau de 0,76 à 2,5 écarts-types. Le marché `p1_total`, qui
n'avait **aucun** biais avant le gel (0,05 écart-type), en a acquis un
significatif après (2,6) — un défaut de modèle n'apparaît pas à une date, un
gel de données si.

Comment la fraîcheur est jugée
------------------------------
Pas contre le calendrier, mais **contre la réalité du terrain** : on demande à
ESPN la date du dernier match effectivement joué, et on la compare à la date
du dernier match présent dans le dataset. Un écart de treize jours en pleine
saison est une panne ; le même écart en juillet n'est rien, et cette
comparaison fait la différence toute seule, sans table de dates de saisons à
maintenir.

Codes de retour : 0 = à jour (ou hors-saison), 1 = retard au-delà du seuil.
Le contrôle ne bloque pas la publication — des prédictions dégradées valent
mieux qu'une app vide — mais il rend le run rouge et l'écrit dans le bilan.

Usage :
    python scripts/check_data_freshness.py --sport nhl
    python scripts/check_data_freshness.py --sport both --max-lag-days 3
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from vizer_core.espn import scoreboard  # noqa: E402

# Au-delà de ce retard, en pleine saison, le modèle décide sur un état du
# championnat qui n'existe plus. Trois jours : la NHL et la NBA jouent presque
# chaque soir, et une fenêtre glissante de dix matchs se renouvelle en une
# semaine.
DEFAULT_MAX_LAG = 3

# Profondeur de la recherche du dernier match joué. Dix jours couvrent une
# pause d'étoiles ou un trou de calendrier sans conclure à tort au hors-saison.
LOOKBACK_DAYS = 10

# Chemin du dataset et noms de colonne de date acceptés, par sport. L'agrégat
# NHL est en format large (une ligne par match, colonnes `_home` / `_away`),
# d'où le suffixe.
DATASETS = {
    'nhl': ('vizer_nhl/data/dataset_agrege_vizer_nhl.csv',
            ('gameDate_home', 'gameDate', 'game_date', 'date')),
    'nba': ('vizer_nba/data/NBA_GAMES.csv',
            ('GAME_DATE', 'game_date')),
}


def dataset_last_game(sport: str, repo: pathlib.Path) -> tuple[date | None, str]:
    """Date du dernier match présent dans le dataset, et la colonne utilisée."""
    rel, candidates = DATASETS[sport]
    path = repo / rel
    if not path.is_file():
        return None, f"{rel} absent"

    import pandas as pd
    # On ne lit que la colonne de date : le dataset NHL pèse 73 Mo et la lire
    # entièrement pour un seul maximum serait absurde dans un job quotidien.
    header = pd.read_csv(path, nrows=0).columns
    column = next((c for c in candidates if c in header), None)
    if column is None:
        return None, f"aucune colonne de date parmi {candidates} dans {rel}"
    series = pd.read_csv(path, usecols=[column])[column]
    parsed = pd.to_datetime(series, errors='coerce').dropna()
    if parsed.empty:
        return None, f"colonne {column} vide ou illisible"
    return parsed.max().date(), column


def last_played(sport: str, today: date, lookback: int = LOOKBACK_DAYS) -> date | None:
    """Date du dernier match terminé selon ESPN, ou None si rien n'a été joué."""
    for offset in range(lookback):
        day = today - timedelta(days=offset)
        try:
            payload = scoreboard(sport, day, timeout=20)
        except Exception as e:
            print(f"  ⚠️  ESPN injoignable pour {day} ({type(e).__name__}: {e})",
                  file=sys.stderr)
            continue
        for event in payload.get('events') or []:
            comps = event.get('competitions') or []
            if not comps:
                continue
            status = (comps[0].get('status') or {}).get('type') or {}
            if status.get('completed'):
                return day
    return None


def check(sport: str, repo: pathlib.Path, today: date,
          max_lag: int) -> tuple[int, dict]:
    """Retourne (code de sortie, verdict publiable)."""
    print(f"🗓️  Fraîcheur des données — {sport.upper()}")
    verdict: dict = {'sport': sport, 'max_lag_days': max_lag}

    last_in_data, note = dataset_last_game(sport, repo)
    if last_in_data is None:
        print(f"  ⚠️  Impossible de conclure : {note}", file=sys.stderr)
        # Une absence de données n'est pas un retard : on ne bloque pas, et on
        # ne crie pas une panne qu'on n'a pas constatée.
        return 0, {**verdict, 'status': 'unknown', 'detail': note}

    verdict['last_in_data'] = last_in_data.isoformat()
    played = last_played(sport, today)
    if played is None:
        print(f"  ✓ dataset au {last_in_data} · aucun match joué depuis "
              f"{LOOKBACK_DAYS} jours — hors-saison, rien à rattraper")
        return 0, {**verdict, 'status': 'offseason'}

    lag = (played - last_in_data).days
    verdict.update({'last_played': played.isoformat(), 'lag_days': lag})
    print(f"  dataset jusqu'au {last_in_data} ({note}) · dernier match joué "
          f"le {played} · retard {lag} jour(s)")

    if lag <= max_lag:
        print("  ✅ à jour")
        return 0, {**verdict, 'status': 'fresh'}

    print(f"\n❌ {sport.upper()} : {lag} jours de retard sur le terrain.",
          file=sys.stderr)
    print("   Le modèle décide sur un état du championnat qui n'existe plus,\n"
          "   et ses fenêtres glissantes ne voient pas les matchs récents.\n"
          "   Le dataset est publié par le PC à IP résidentielle — seul point\n"
          "   d'accès, les deux fournisseurs bloquant les IP de datacenter.\n"
          "   Rattrapage immédiat :\n"
          f"     systemctl --user start vizer-dataset-{sport}\n"
          f"   ou à la main : vizer_{sport}/scripts/push_dataset_to_kaggle.py\n"
          "   Mise en place des timers : deploy/systemd/README.md",
          file=sys.stderr)
    return 1, {**verdict, 'status': 'stale'}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Compare la dernière date du dataset au dernier match joué.")
    ap.add_argument('--sport', default='both', choices=['nhl', 'nba', 'both'])
    ap.add_argument('--max-lag-days', type=int, default=DEFAULT_MAX_LAG)
    ap.add_argument('--today', default=None, help="Date de référence (YYYY-MM-DD)")
    ap.add_argument('--out', default=None,
                    help="Écrit le verdict en JSON (pour performance/freshness.json)")
    args = ap.parse_args(argv)

    repo = pathlib.Path(__file__).resolve().parent.parent
    today = date.fromisoformat(args.today) if args.today else date.today()
    sports = ('nhl', 'nba') if args.sport == 'both' else (args.sport,)

    verdicts: dict[str, dict] = {}
    stale: list[str] = []
    for sport in sports:
        code, verdict = check(sport, repo, today, args.max_lag_days)
        verdicts[sport] = verdict
        if code:
            stale.append(sport)

    # Le verdict est publié parce que l'alerte doit venir du cloud : la panne
    # qu'on surveille est « le PC était éteint », et un PC éteint ne peut pas
    # prévenir qu'il l'était. C'est le cron Vercel qui lit ce fichier et
    # pousse la notification.
    if args.out:
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'stale': sorted(stale),
            'sports': verdicts,
        }, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"✅ {out}", file=sys.stderr)

    if stale:
        print(f"\n🛑 Données en retard : {', '.join(s.upper() for s in stale)}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
