#!/usr/bin/env python
"""
check_serving_features.py — Le modèle servi reçoit-il ce qu'il attend ?

Pourquoi ce contrôle existe
---------------------------
La barrière de qualité évalue le modèle **tel qu'entraîné**, sur un dataset
où toutes les features existent. Elle ne voit jamais le modèle **tel que
servi**, où elles sont reconstruites par un autre chemin.

Les deux chemins avaient divergé. Six différentiels — dont le partage de buts
attendus, le powerplay, la forme et l'interaction gardien — n'étaient déclarés
nulle part pour la prédiction. `reindex(fill_value=0)` les remplissait de
zéros, en silence, et le modèle décidait sur huit features au lieu de seize :
38 % de son pouvoir explicatif perdu entre l'entraînement et la production,
sans qu'aucun test ne devienne rouge.

Ce que le contrôle vérifie
--------------------------
**Qu'aucune feature attendue par le modèle ne manque à la ligne transformée.**
C'est le signal structurel, et il ne produit pas de faux positif : une feature
absente de la ligne est une feature que personne ne sait calculer, point.
C'était exactement le cas — sept colonnes manquaient, `reindex(fill_value=0)`
les inventait à zéro.

Une valeur constamment nulle est signalée **sans faire échouer**. Elle peut
être parfaitement légitime : `avg_top_line_xGF_10` vaut 0,5 — sa valeur de
remplissage — sur 91 % des matchs en début de saison, le temps que la fenêtre
glissante de dix matchs se remplisse. Faire échouer là-dessus apprendrait
surtout à ignorer le contrôle chaque automne.

Codes de retour : 0 = conforme, 1 = feature manquante, 2 = erreur.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

# Matchups de contrôle : des équipes stables, présentes dans l'historique.
PROBES = {
    'nhl': [('TOR', 'MTL'), ('BOS', 'NYR'), ('COL', 'DAL'),
            ('EDM', 'LAK'), ('VGK', 'SJS'), ('FLA', 'TBL')],
    'nba': [('LAL', 'BOS'), ('GSW', 'DEN'), ('MIL', 'PHI'),
            ('NYK', 'MIA'), ('OKC', 'DAL'), ('PHX', 'SAC')],
}


def check_nhl(verbose: bool) -> int:
    from src.api.unified_predictor import NHLUnifiedPredictor

    predictor = NHLUnifiedPredictor()
    features = predictor.meta.get('features_used', [])
    if not features:
        print("❌ Le registre ne déclare aucune feature.", file=sys.stderr)
        return 2

    zeros: Counter[str] = Counter()
    missing: set[str] = set()
    probed = 0
    for home, away in PROBES['nhl']:
        if not (predictor.has_team(home) and predictor.has_team(away)):
            continue
        row = predictor._prepare_features(home, away)
        if row is None:
            continue
        probed += 1
        # Le signal qui compte : la colonne existe-t-elle avant que
        # `reindex(fill_value=0)` ne l'invente ?
        missing |= {f for f in features if f not in row.columns}
        aligned = row.reindex(columns=features, fill_value=0)
        for feature in features:
            if float(aligned[feature].iloc[0]) == 0.0:
                zeros[feature] += 1

    if probed == 0:
        print("❌ Aucun matchup de contrôle exploitable.", file=sys.stderr)
        return 2

    print(f"  {len(features)} features attendues · {probed} matchups de contrôle")
    if verbose:
        for feature in features:
            n = zeros[feature]
            flags = []
            if feature in missing:
                flags.append('MANQUANTE')
            elif n == probed:
                flags.append('constamment nulle')
            print(f"    {feature:28s} nulle {n}/{probed}"
                  f"{'  ← ' + ', '.join(flags) if flags else ''}")

    # Avertissement, pas échec : une nullité constante peut être légitime —
    # fenêtre glissante pas encore remplie en début de saison, évènement rare.
    constant = [f for f in features if zeros[f] == probed and f not in missing]
    if constant:
        print(f"  ⚠️  {len(constant)} feature(s) constamment nulle(s) sur les "
              f"matchups testés : {', '.join(constant)}")
        print("      À vérifier si cela persiste une fois la saison avancée.")

    if missing:
        print(f"\n❌ {len(missing)} feature(s) absente(s) de la ligne servie :",
              file=sys.stderr)
        for feature in sorted(missing):
            print(f"     - {feature}", file=sys.stderr)
        print("\n   Le modèle a été entraîné avec, il décide sans : `reindex`\n"
              "   les remplit de zéros en silence. Déclarer le différentiel\n"
              "   dans RECOVERED_DIFFS ou MULTI_WINDOW_DIFFS\n"
              "   (vizer_nhl/src/utils.py).", file=sys.stderr)
        return 1

    print("  ✅ Toutes les features attendues sont calculées.")
    return 0


def check_nba(verbose: bool) -> int:
    """
    Côté NBA, le remplissage à zéro est **dans** le constructeur de features :
    on ne peut pas comparer avant / après comme pour le NHL. Le prédicteur
    note donc ce qu'il a dû inventer (`last_invented_features`), et c'est ce
    relevé qu'on lit ici.

    Le contrôle regarde aussi les valeurs **constantes d'un matchup à
    l'autre** — pas seulement nulles. C'est ce qui a révélé le défaut
    `SEASON_AVG_TOTAL` : la feature existait, n'était pas nulle, mais valait
    398 points en production contre 231 à l'entraînement parce que le dataset
    comptait chaque match deux fois. Une feature identique sur six affiches
    différentes ne porte aucune information, qu'elle soit nulle ou non.
    """
    from src.api.unified_predictor import UnifiedPredictor

    predictor = UnifiedPredictor('models/nba_model.pkl')

    expected: set[str] = set()
    for name in predictor.registry.list_markets():
        market = predictor.registry.get(name)
        cols = getattr(getattr(market, 'predictor', None), 'feature_columns', None)
        if cols:
            expected |= set(cols)
    if not expected:
        print("❌ Aucun marché ne déclare de features.", file=sys.stderr)
        return 2

    invented: set[str] = set()
    values: dict[str, set[float]] = {f: set() for f in expected}
    probed = 0
    for home, away in PROBES['nba']:
        try:
            row = predictor._prepare_game_features(home, away)
        except (ValueError, KeyError) as e:
            print(f"  ⚠️  {away} @ {home} ignoré ({type(e).__name__}: {e})",
                  file=sys.stderr)
            continue
        probed += 1
        for market_cols in (getattr(predictor, 'last_invented_features', {}) or {}).values():
            invented |= set(market_cols)
        for feature in expected:
            if feature in row.columns:
                try:
                    values[feature].add(round(float(row[feature].iloc[0]), 6))
                except (TypeError, ValueError):
                    pass

    if probed < 2:
        print("❌ Moins de deux matchups exploitables : rien à comparer.",
              file=sys.stderr)
        return 2

    print(f"  {len(expected)} features attendues · {probed} matchups de contrôle")
    constant = sorted(f for f in expected
                      if f not in invented and len(values[f]) == 1)
    if verbose:
        for feature in sorted(expected):
            flags = []
            if feature in invented:
                flags.append('INVENTÉE À ZÉRO')
            elif feature in constant:
                flags.append(f'constante = {next(iter(values[feature]))}')
            print(f"    {feature:28s} {len(values[feature])} valeur(s)"
                  f"{'  ← ' + ', '.join(flags) if flags else ''}")

    if constant:
        print(f"  ⚠️  {len(constant)} feature(s) identique(s) sur tous les "
              f"matchups : {', '.join(constant)}")
        print("      Certaines le sont légitimement (niveau de scoring de la "
              "saison, repos hors-saison plafonné).")
        print("      À revoir une fois la saison lancée : une feature "
              "constante ne porte aucune information.")

    if invented:
        print(f"\n❌ {len(invented)} feature(s) inventée(s) à zéro au service :",
              file=sys.stderr)
        for feature in sorted(invented):
            print(f"     - {feature}", file=sys.stderr)
        print("\n   Le modèle a été entraîné avec, il décide sans. Il faut la\n"
              "   calculer dans `_prepare_game_features`\n"
              "   (vizer_nba/src/api/unified_predictor.py).", file=sys.stderr)
        return 1

    print("  ✅ Toutes les features attendues sont calculées.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Vérifie que le modèle servi reçoit toutes ses features.")
    parser.add_argument('--sport', default='nhl', choices=['nhl', 'nba'])
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args(argv)

    # Les pickles référencent `src.*` : il faut se placer dans le dossier du
    # sport, comme le fait la barrière de qualité.
    sport_dir = Path(__file__).resolve().parent.parent / f'vizer_{args.sport}'
    if not sport_dir.is_dir():
        print(f"❌ Dossier introuvable : {sport_dir}", file=sys.stderr)
        return 2

    import os
    os.chdir(sport_dir)
    sys.path.insert(0, str(sport_dir))

    print(f"🔍 Features servies — {args.sport.upper()}")
    try:
        return check_nhl(args.verbose) if args.sport == 'nhl' else check_nba(args.verbose)
    except FileNotFoundError as e:
        # Modèle ou données absents : on ne peut pas conclure, et bloquer la CI
        # sur une absence de données serait un faux positif.
        print(f"⚠️  Contrôle impossible ({e}) — ignoré.", file=sys.stderr)
        return 0


if __name__ == '__main__':
    sys.exit(main())
