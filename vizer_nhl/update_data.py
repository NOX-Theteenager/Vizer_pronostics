#!/usr/bin/env python
"""
update_data.py — Reconstruit ou met à jour le dataset NHL agrégé.

Remplace les notebooks 01_Maintenance + 02_Agregation (+ 02b optionnel) par
une commande unique. Deux modes :

  --mode update  (défaut) : télécharge les données fraîches de la saison
                            courante puis ré-agrège le dataset complet.
  --mode rebuild          : ré-agrège uniquement depuis les CSVs locaux
                            (sans téléchargement).

Usage :
    python update_data.py                       # update complet (download + agrège)
    python update_data.py --mode rebuild        # ré-agrège local seulement
    python update_data.py --season 2025         # précise la saison courante
    python update_data.py --with-shots          # télécharge aussi les shots (P1)
    python update_data.py --no-download         # alias de --mode rebuild
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

try:
    from vizer_core import load_config
except Exception:
    load_config = None

from src.data.downloader import MoneypuckDownloader
from src.data.aggregator import NHLAggregator
from src.data.period_aggregator import PeriodAggregator


def main():
    parser = argparse.ArgumentParser(description="MAJ / reconstruction du dataset NHL")
    parser.add_argument('--config', default='config.yaml')
    parser.add_argument('--mode', choices=['update', 'rebuild'], default='update',
                        help="'update' = download + agrège ; 'rebuild' = agrège local")
    parser.add_argument('--season', type=int, default=None,
                        help="Année de la saison courante (défaut: auto-détectée)")
    parser.add_argument('--with-shots', action='store_true',
                        help="Télécharge aussi les fichiers shots (pour period_stats / P1)")
    parser.add_argument('--no-download', action='store_true',
                        help="Alias de --mode rebuild (pas de téléchargement)")
    parser.add_argument('--data-dir', default=None)
    args = parser.parse_args()

    if args.no_download:
        args.mode = 'rebuild'

    # Détection auto de la saison NHL si non précisée
    from src.season import current_nhl_season, is_offseason, detect_available_seasons
    if args.season is None:
        args.season = current_nhl_season()
        auto_note = " (auto-détectée)"
    else:
        auto_note = ""

    # Config (data_dir + filename)
    data_dir = args.data_dir or 'data'
    output_filename = 'dataset_agrege_vizer_nhl.csv'
    if load_config is not None:
        try:
            config = load_config(args.config, validate=False)
            paths = config.get('paths', {})
            data_dir = args.data_dir or paths.get('data_dir', 'data')
            output_filename = paths.get('dataset_filename', output_filename)
        except Exception:
            pass

    t0 = time.time()
    print("=" * 70)
    print("🏒 MISE À JOUR DU DATASET NHL")
    print("=" * 70)
    print(f"Mode      : {args.mode}")
    print(f"Saison    : {args.season}{auto_note}")
    print(f"Data dir  : {data_dir}")
    print(f"Sortie    : {output_filename}")

    if is_offseason():
        print("\nℹ️  Intersaison NHL (juillet-septembre) : pas de nouveaux matchs "
              "attendus avant octobre.")

    # Détecter les saisons déjà présentes localement
    local_seasons = detect_available_seasons(data_dir, category='skaters')
    if local_seasons:
        print(f"Saisons locales détectées : {local_seasons[0]}–{local_seasons[-1]} "
              f"({len(local_seasons)} saisons)")
        if args.season not in local_seasons and args.mode == 'update':
            print(f"🆕 Nouvelle saison {args.season} détectée — sera téléchargée.")

    # ── Étape 1 : Téléchargement (mode update seulement) ──
    if args.mode == 'update':
        print(f"\n⬇️  Téléchargement des données saison {args.season}...")
        print("-" * 70)
        dl = MoneypuckDownloader(data_dir=data_dir, season=args.season)
        dl.update_current_season()
        if args.with_shots:
            print(f"\n⬇️  Téléchargement des shots (period data)...")
            dl.download_shots(historical=False)
    else:
        print("\nℹ️  Mode rebuild : pas de téléchargement, ré-agrégation locale.")

    # ── Étape 1b : Agrégation des tirs → period_stats (réplique 02b) ──
    # On l'exécute si des fichiers shots sont présents (téléchargés ou locaux),
    # AVANT l'agrégation principale, pour que period_stats.csv soit prêt à être
    # fusionné (goals_p1) par NHLAggregator._merge_period_stats.
    shots_present = bool(list(Path(data_dir).glob('shots_*.csv')))
    if args.with_shots or shots_present:
        print(f"\n🎯 Agrégation des tirs → period_stats (1re période)...")
        print("-" * 70)
        try:
            PeriodAggregator(data_dir=data_dir, verbose=True).build(save=True)
        except Exception as e:
            print(f"⚠️  Échec agrégation des tirs ({e}). "
                  f"Les markets P1 utiliseront le fallback 30%.", file=sys.stderr)

    # ── Étape 2 : Agrégation du dataset principal ──
    print(f"\n🔧 Agrégation du dataset...")
    print("-" * 70)
    agg = NHLAggregator(data_dir=data_dir, verbose=True)
    try:
        df_final = agg.build(save=True, output_filename=output_filename)
    except FileNotFoundError as e:
        print(f"\n❌ Fichier manquant : {e}", file=sys.stderr)
        print("   Vérifie que les CSVs Moneypuck sont dans le dossier data/.", file=sys.stderr)
        print("   (all_teams.csv, goalies_*, skaters_*, lines_*)", file=sys.stderr)
        return 1

    # ── Récap ──
    print("\n" + "=" * 70)
    print("✅ TERMINÉ")
    print("=" * 70)
    print(f"  Dataset : {Path(data_dir) / output_filename}")
    print(f"  Matchs  : {len(df_final):,}")
    has_p1 = 'goals_p1_home' in df_final.columns
    print(f"  Data P1 : {'OUI (mode dedicated)' if has_p1 else 'NON (fallback 30%)'}")
    print(f"  Durée   : {time.time() - t0:.1f}s")
    print(f"\n➡️  Tu peux maintenant relancer : python train.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
