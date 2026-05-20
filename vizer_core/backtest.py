"""
backtest.py — Walk-forward backtest des marchés Vizer (sport-agnostic).

Permet d'évaluer la profitabilité réelle d'un ensemble de marchés sur un dataset
historique, en simulant les paris avec mise Kelly et en calculant ROI / drawdown
/ Sharpe / calibration.

Trois modes :

  A. CALIBRATION CHECK (sans cotes)
     - "Quand le modèle dit 70%, gagne-t-il vraiment 70% ?"
     - Bucketing des probas prédites + comparaison avec win rate empirique
     - Output : table calibration + Brier décomposé (reliability + resolution)

  B. vs BOOKMAKER SYNTHÉTIQUE
     - Génère des cotes "marché efficient" basées sur la baseline league
       (home advantage, line médiane) + bruit + vig
     - Simule les paris détectés comme value bets
     - Output : ROI cumulé, drawdown, Sharpe, win rate
     - Si on bat un book naïf à 55% → on a du signal. Sinon : pas d'edge réel.

  C. vs COTES RÉELLES (interface)
     - L'utilisateur fournit un OddsProvider qui retourne les cotes archivées
       pour chaque match. C'est le test ultime.

Architecture :
    OddsProvider (interface)            → fournit les cotes
        ├── SyntheticOddsProvider       → mode B (book naïf)
        ├── CSVOddsProvider             → mode C (cotes archivées)
        └── NullOddsProvider            → mode A (calibration seule)

    Backtester(registry, config)        → moteur principal
        .run(test_df, features_fn, ...) → BacktestResult

    BetRecord                           → un pari individuel
    BacktestResult                      → agrégation + rapport
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Callable, Optional

import math
import numpy as np
import pandas as pd

from .market_base import MarketBase, MarketPrediction, ValueBet
from .model_registry import ModelRegistry


# =========================================================================
# Datasets de sortie
# =========================================================================

@dataclass
class BetRecord:
    """Un pari individuel résolu (gagné ou perdu)."""
    match_id: str
    date: str
    home: str
    away: str
    market: str
    selection: str
    model_proba: float
    book_proba: float        # = 1/odds (implicite, sans vig)
    book_odds: float
    edge: float
    kelly_stake_fraction: float   # fraction du bankroll
    stake_amount: float           # unités absolues
    outcome: int                  # 1 = win, 0 = loss
    pnl: float                    # +stake*(odds-1) ou -stake
    bankroll_before: float
    bankroll_after: float


@dataclass
class CalibrationBucket:
    """Pour le calibration plot : groupe les probas par tranches de 10%."""
    proba_low: float           # ex: 0.5
    proba_high: float          # ex: 0.6
    n_predictions: int
    n_wins: int
    avg_proba_predicted: float
    actual_win_rate: float
    is_calibrated: bool        # |predicted - actual| < 5%


@dataclass
class MarketBacktestSummary:
    """Résumé du backtest pour un marché donné."""
    market_name: str
    total_predictions: int
    total_bets: int             # paris pris (value bets détectés)
    bet_rate: float             # bets / predictions
    wins: int
    win_rate: float
    avg_odds: float
    total_staked: float
    total_pnl: float
    roi: float                  # pnl / staked
    brier_score: Optional[float] = None  # qualité des probas (mode A)
    avg_edge: float = 0.0
    avg_kelly: float = 0.0


@dataclass
class BacktestResult:
    """Résultat agrégé du backtest."""
    config: dict
    initial_bankroll: float
    final_bankroll: float
    total_pnl: float
    roi_pct: float
    n_matches: int
    bets: list[BetRecord] = field(default_factory=list)
    per_market: dict[str, MarketBacktestSummary] = field(default_factory=dict)
    calibration: dict[str, list[CalibrationBucket]] = field(default_factory=dict)
    bankroll_curve: list[float] = field(default_factory=list)
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0

    def to_dataframe(self) -> pd.DataFrame:
        """Sérialise les paris en DataFrame pour analyse externe."""
        return pd.DataFrame([asdict(b) for b in self.bets])

    def print_summary(self) -> None:
        """Affiche un rapport synthétique dans la console."""
        print("=" * 70)
        print("📊 RÉSULTAT BACKTEST")
        print("=" * 70)
        print(f"Matchs analysés    : {self.n_matches:,}")
        print(f"Paris pris         : {len(self.bets):,}")
        print(f"Bankroll initial   : {self.initial_bankroll:.2f}")
        print(f"Bankroll final     : {self.final_bankroll:.2f}")
        print(f"P&L total          : {self.total_pnl:+.2f}")
        print(f"ROI                : {self.roi_pct:+.2f}%")
        print(f"Drawdown max       : {self.max_drawdown_pct:.2f}%")
        print(f"Sharpe ratio       : {self.sharpe_ratio:.2f}")
        print()
        print("Par marché :")
        print("-" * 70)
        header = f"{'Market':<20} {'Bets':>6} {'WinRate':>8} {'AvgOdds':>8} {'ROI':>8} {'Brier':>8}"
        print(header)
        print("-" * 70)
        for name, s in sorted(self.per_market.items()):
            brier_str = f"{s.brier_score:.4f}" if s.brier_score is not None else "  —  "
            roi_str = f"{s.roi:+.2%}" if s.total_staked > 0 else "  —  "
            wr_str = f"{s.win_rate:.1%}" if s.total_bets > 0 else "  —  "
            print(f"{name:<20} {s.total_bets:>6} {wr_str:>8} "
                  f"{s.avg_odds:>8.2f} {roi_str:>8} {brier_str:>8}")
        print()
        if self.calibration:
            self._print_calibration()

    def _print_calibration(self) -> None:
        print("Calibration (par marché) :")
        print("-" * 70)
        for market, buckets in self.calibration.items():
            if not buckets:
                continue
            print(f"\n  {market}")
            print(f"    {'Range':<14} {'n':>5} {'pred':>7} {'actual':>7} {'OK?':>4}")
            for b in buckets:
                pred = f"{b.avg_proba_predicted:.3f}"
                actual = f"{b.actual_win_rate:.3f}"
                ok = "✓" if b.is_calibrated else "✗"
                range_str = f"[{b.proba_low:.2f}-{b.proba_high:.2f})"
                print(f"    {range_str:<14} {b.n_predictions:>5} "
                      f"{pred:>7} {actual:>7} {ok:>4}")


# =========================================================================
# OddsProviders
# =========================================================================

class OddsProvider(ABC):
    """Interface pour fournir des cotes pour un match donné."""

    @abstractmethod
    def get_odds(
        self,
        market: MarketBase,
        match_context: dict,
        prediction: MarketPrediction,
    ) -> dict[str, float] | None:
        """
        Retourne {selection: odds_decimal} pour ce match et ce marché.
        None si pas de cotes disponibles → on skip le pari.
        """


class NullOddsProvider(OddsProvider):
    """Mode A : pas de cotes. Backtest = calibration check seulement."""

    def get_odds(self, market, match_context, prediction):
        return None


class SyntheticOddsProvider(OddsProvider):
    """
    Mode B : cotes synthétiques pour benchmark.

    Génère un "book naïf" qui mélange :
    - une baseline league (ex: home win rate 57.5%, total moyen 224.5)
    - du bruit gaussien (le book a aussi de l'incertitude)
    - un vig (marge bookmaker, typiquement 4.5%)

    Si le modèle bat ce book → bon signe. Si non, pas d'edge.
    """

    def __init__(
        self,
        vig: float = 0.045,
        moneyline_home_baseline: float = 0.575,   # home win rate league NBA
        total_baseline_line: float = 224.5,        # ligne médiane NBA 2024-25
        home_team_total_baseline: float = 113.0,
        away_team_total_baseline: float = 111.5,
        noise_proba: float = 0.05,                  # σ bruit sur P_book
        noise_total: float = 4.0,                   # σ bruit sur la ligne totale
        seed: int = 42,
    ):
        self.vig = vig
        self.ml_home_baseline = moneyline_home_baseline
        self.total_line = total_baseline_line
        self.htt_line = home_team_total_baseline
        self.att_line = away_team_total_baseline
        self.noise_proba = noise_proba
        self.noise_total = noise_total
        self.rng = np.random.default_rng(seed)

    def _odds_with_vig(self, p_no_vig: float) -> float:
        """Convertit une proba fair en cote avec vig. p×(1+vig) puis 1/."""
        # Cote équitable
        if p_no_vig <= 0:
            return 100.0  # cote astronomique
        fair_odds = 1.0 / p_no_vig
        # Cote avec vig (book réduit la cote, son edge)
        return fair_odds / (1 + self.vig)

    def get_odds(self, market, match_context, prediction):
        name = market.name
        if name in ('moneyline', 'win'):
            # Book naïf = baseline + bruit
            p_home = float(np.clip(
                self.ml_home_baseline + self.rng.normal(0, self.noise_proba),
                0.20, 0.80,
            ))
            p_away = 1 - p_home
            return {
                'home': self._odds_with_vig(p_home),
                'away': self._odds_with_vig(p_away),
            }

        if name == 'total':
            # Book a une ligne ~ baseline + bruit, et calcule O/U via gaussien
            book_line = self.total_line + self.rng.normal(0, self.noise_total)
            # Cotes O/U équilibrées autour de la ligne du book : 50/50
            # Mais le predicted total est différent → on est sur la ligne book
            # Pour matcher l'usage de TotalMarket : la "selection" sera
            # 'over_<line_used>' où line_used est la default_line du market.
            # Donc on retourne les cotes pour la ligne par défaut du market.
            line = prediction.metadata.get('line_used', self.total_line)
            # Proba book naïve : 50/50 sur sa ligne, ajustée selon écart à la ligne du modèle
            # Plus la ligne demandée est haute par rapport à book_line, moins p_over book
            sigma_book = 18.0
            z = (line - book_line) / sigma_book
            p_under_book = 0.5 * (1 + math.erf(z / math.sqrt(2)))
            p_over_book = 1 - p_under_book
            return {
                f'over_{line}': self._odds_with_vig(p_over_book),
                f'under_{line}': self._odds_with_vig(p_under_book),
            }

        if name == 'total_poisson':
            # Réutiliser la même mécanique que 'total'
            line = prediction.metadata.get('line_used', self.total_line)
            book_line = self.total_line + self.rng.normal(0, self.noise_total)
            sigma_book = 18.0
            z = (line - book_line) / sigma_book
            p_under_book = 0.5 * (1 + math.erf(z / math.sqrt(2)))
            p_over_book = 1 - p_under_book
            return {
                f'over_{line}': self._odds_with_vig(p_over_book),
                f'under_{line}': self._odds_with_vig(p_under_book),
            }

        if name == 'home_team_total':
            line = prediction.metadata.get('line_used', self.htt_line)
            book_line = self.htt_line + self.rng.normal(0, self.noise_total / 2)
            sigma_book = 12.0
            z = (line - book_line) / sigma_book
            p_under_book = 0.5 * (1 + math.erf(z / math.sqrt(2)))
            p_over_book = 1 - p_under_book
            return {
                f'over_{line}': self._odds_with_vig(p_over_book),
                f'under_{line}': self._odds_with_vig(p_under_book),
            }

        if name == 'away_team_total':
            line = prediction.metadata.get('line_used', self.att_line)
            book_line = self.att_line + self.rng.normal(0, self.noise_total / 2)
            sigma_book = 12.0
            z = (line - book_line) / sigma_book
            p_under_book = 0.5 * (1 + math.erf(z / math.sqrt(2)))
            p_over_book = 1 - p_under_book
            return {
                f'over_{line}': self._odds_with_vig(p_over_book),
                f'under_{line}': self._odds_with_vig(p_under_book),
            }

        # Market inconnu → pas de cotes
        return None


class CSVOddsProvider(OddsProvider):
    """
    Mode C : charge des cotes historiques depuis un CSV.

    Format attendu :
        match_id, market, selection, odds
        '0022500001', 'moneyline', 'home', 1.75
        '0022500001', 'moneyline', 'away', 2.15
        '0022500001', 'total', 'over_224.5', 1.91
        '0022500001', 'total', 'under_224.5', 1.91
        ...
    """

    def __init__(self, csv_path: str):
        self.df = pd.read_csv(csv_path, dtype={'match_id': str})
        # Indexer pour lookup rapide
        self._index: dict[tuple[str, str, str], float] = {}
        for _, row in self.df.iterrows():
            key = (str(row['match_id']), row['market'], row['selection'])
            self._index[key] = float(row['odds'])

    def get_odds(self, market, match_context, prediction):
        match_id = str(match_context.get('match_id', ''))
        if not match_id:
            return None
        result = {}
        for sel in prediction.probabilities.keys():
            key = (match_id, market.name, sel)
            if key in self._index:
                result[sel] = self._index[key]
        return result if result else None


# =========================================================================
# Configuration
# =========================================================================

@dataclass
class BacktestConfig:
    """Paramètres du backtest."""
    initial_bankroll: float = 1000.0
    max_bet_fraction: float = 0.03         # cap dur sur mise Kelly (3% bankroll)
    edge_threshold_override: Optional[float] = None  # si None, utilise edge_threshold du market
    kelly_factor_override: Optional[float] = None    # idem pour Kelly factor
    stop_loss_pct: Optional[float] = None  # arrête le backtest si drawdown > X%
    verbose: bool = True
    calibration_buckets: tuple[float, ...] = (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.90, 1.0)
    # Mode de mise :
    #   'kelly_initial' (défaut) : stake = initial_bankroll × kelly_fraction (unités fixes, RÉALISTE)
    #   'kelly_current'          : stake = current_bankroll × kelly_fraction (compound, peut exploser)
    #   'flat'                   : stake = initial_bankroll × max_bet_fraction (toujours la même)
    stake_mode: str = 'kelly_initial'
    # Edge max accepté (sanity : si edge > 0.25 c'est probablement un bug de cotes)
    edge_cap: float = 0.25


# =========================================================================
# Moteur Backtester
# =========================================================================

class Backtester:
    """
    Moteur de backtest walk-forward.

    Utilisation :
        bt = Backtester(registry, config)
        result = bt.run(
            test_df=features_df,
            outcome_fn=lambda row, market, sel: bool_did_win(row, market, sel),
            features_row_fn=lambda row: row.to_frame().T,
            odds_provider=SyntheticOddsProvider(),
        )
        result.print_summary()
    """

    def __init__(self, registry: ModelRegistry, config: BacktestConfig):
        self.registry = registry
        self.config = config

    def run(
        self,
        test_df: pd.DataFrame,
        outcome_fn: Callable[[pd.Series, str, str], Optional[bool]],
        features_row_fn: Optional[Callable[[pd.DataFrame], pd.DataFrame]] = None,
        odds_provider: Optional[OddsProvider] = None,
        markets: Optional[list[str]] = None,
    ) -> BacktestResult:
        """
        Lance le backtest.

        Args:
            test_df         : DataFrame de matchs (déjà engineerés).
            outcome_fn      : (row_series, market_name, selection) → True/False/None
                              True = la sélection a gagné, None = indéterminable.
            features_row_fn : (row_df) → pd.DataFrame d'une ligne pour predict()
                              Si None, on utilise test_df.iloc[[idx]] tel quel
                              (préserve les dtypes — recommandé).
            odds_provider   : fournisseur de cotes (NullOddsProvider si None)
            markets         : liste des markets à backtester (par défaut tous activés)
        """
        if odds_provider is None:
            odds_provider = NullOddsProvider()
        if markets is None:
            markets = [m for m in self.registry.list_markets()
                       if self.registry.get(m).enabled]

        if self.config.verbose:
            print(f"🔁 Backtest sur {len(test_df):,} matchs, {len(markets)} marché(s)")
            print(f"   Markets : {markets}")
            print(f"   Bankroll initial : {self.config.initial_bankroll:.2f}")

        bankroll = self.config.initial_bankroll
        bankroll_curve = [bankroll]
        max_bankroll = bankroll
        max_drawdown = 0.0
        bets: list[BetRecord] = []

        calibration_data: dict[str, list[tuple[float, int]]] = defaultdict(list)
        brier_data: dict[str, list[tuple[float, int]]] = defaultdict(list)

        # Tri chronologique pour walk-forward correct
        if 'GAME_DATE' in test_df.columns:
            test_df = test_df.sort_values('GAME_DATE').reset_index(drop=True)
        else:
            test_df = test_df.reset_index(drop=True)

        n_predictions_per_market: dict[str, int] = defaultdict(int)
        n_pred_failures = 0
        first_failure_msg = None

        for idx in range(len(test_df)):
            # CRITIQUE : utiliser iloc[[idx]] qui préserve les dtypes (vs row.to_frame().T qui les casse)
            row_df = test_df.iloc[[idx]]
            row = test_df.iloc[idx]  # Series pour outcome_fn

            match_id = str(row.get('GAME_ID', f'idx_{idx}'))
            date = str(row.get('GAME_DATE', ''))
            home = str(row.get('HOME_TEAM_ABBREVIATION', row.get('HOME_TEAM_ID', '?')))
            away = str(row.get('AWAY_TEAM_ABBREVIATION', row.get('AWAY_TEAM_ID', '?')))

            # features_row_fn optionnel pour transformations supplémentaires
            features_row = features_row_fn(row_df) if features_row_fn else row_df

            for market_name in markets:
                market = self.registry.get(market_name)
                if not market.enabled or not market.is_fitted:
                    continue

                try:
                    prediction = market.predict(home, away, context={'features_row': features_row})
                except Exception as e:
                    n_pred_failures += 1
                    if first_failure_msg is None:
                        first_failure_msg = f"market={market_name} match={match_id}: {type(e).__name__}: {str(e)[:300]}"
                    continue

                n_predictions_per_market[market_name] += 1

                for selection, proba in prediction.probabilities.items():
                    outcome = outcome_fn(row, market_name, selection)
                    if outcome is not None:
                        calibration_data[market_name].append((proba, int(outcome)))
                        brier_data[market_name].append((proba, int(outcome)))

                odds_dict = odds_provider.get_odds(market, {'match_id': match_id}, prediction)
                if not odds_dict:
                    continue

                for selection, odds in odds_dict.items():
                    if selection not in prediction.probabilities:
                        continue
                    if odds <= 1.0:
                        continue

                    edge_thresh = self.config.edge_threshold_override
                    if edge_thresh is not None:
                        p_model = prediction.probabilities[selection]
                        p_implied = 1.0 / odds
                        edge = p_model - p_implied
                        if edge < edge_thresh:
                            continue
                        kelly = (p_model * (odds - 1) - (1 - p_model)) / (odds - 1)
                        if self.config.kelly_factor_override:
                            kelly *= self.config.kelly_factor_override
                        else:
                            kelly *= market.kelly_factor
                        kelly = max(0.0, min(kelly, self.config.max_bet_fraction))
                        if kelly <= 0:
                            continue
                        vb = ValueBet(
                            market_name=market.name,
                            selection=selection,
                            predicted_proba=p_model,
                            bookmaker_odds=odds,
                            implied_proba=p_implied,
                            edge=edge,
                            kelly_stake=kelly,
                            expected_value_per_unit=edge * odds,
                            confidence=prediction.confidence,
                        )
                    else:
                        vb = market.value_bet(prediction, selection, odds)
                        if vb is None:
                            continue
                        capped = min(vb.kelly_stake, self.config.max_bet_fraction)
                        if capped <= 0:
                            continue
                        vb.kelly_stake = capped

                    outcome = outcome_fn(row, market_name, selection)
                    if outcome is None:
                        continue

                    # Sanity : si l'edge est aberrant, on skip (probable bug cotes)
                    if vb.edge > self.config.edge_cap:
                        continue

                    # Calcul de la mise selon le mode
                    if self.config.stake_mode == 'kelly_initial':
                        # Unités fixes basées sur bankroll initial (réaliste, pas d'explosion)
                        stake = self.config.initial_bankroll * vb.kelly_stake
                    elif self.config.stake_mode == 'flat':
                        # Toujours la même mise (très conservateur)
                        stake = self.config.initial_bankroll * self.config.max_bet_fraction
                    elif self.config.stake_mode == 'kelly_current':
                        # Kelly compound (peut exploser, utilisable surtout en R&D)
                        stake = bankroll * vb.kelly_stake
                    else:
                        stake = self.config.initial_bankroll * vb.kelly_stake

                    if outcome:
                        pnl = stake * (odds - 1)
                    else:
                        pnl = -stake
                    bankroll_after = bankroll + pnl

                    bets.append(BetRecord(
                        match_id=match_id, date=date, home=home, away=away,
                        market=market_name, selection=selection,
                        model_proba=vb.predicted_proba,
                        book_proba=vb.implied_proba,
                        book_odds=odds,
                        edge=vb.edge,
                        kelly_stake_fraction=vb.kelly_stake,
                        stake_amount=stake,
                        outcome=int(outcome),
                        pnl=pnl,
                        bankroll_before=bankroll,
                        bankroll_after=bankroll_after,
                    ))
                    bankroll = bankroll_after
                    bankroll_curve.append(bankroll)

                    if bankroll > max_bankroll:
                        max_bankroll = bankroll
                    dd = (max_bankroll - bankroll) / max_bankroll
                    if dd > max_drawdown:
                        max_drawdown = dd

                    if self.config.stop_loss_pct and max_drawdown >= self.config.stop_loss_pct:
                        if self.config.verbose:
                            print(f"  🛑 Stop loss déclenché à {max_drawdown:.2%}")
                        return self._build_result(
                            bets, bankroll, bankroll_curve, max_drawdown,
                            len(test_df), markets, calibration_data, brier_data,
                            n_predictions_per_market,
                        )

        if n_pred_failures > 0 and self.config.verbose:
            print(f"  ⚠️  {n_pred_failures} échecs de prédiction. Premier : {first_failure_msg}")

        return self._build_result(
            bets, bankroll, bankroll_curve, max_drawdown,
            len(test_df), markets, calibration_data, brier_data,
            n_predictions_per_market,
        )

    def _build_result(
        self,
        bets: list[BetRecord],
        final_bankroll: float,
        bankroll_curve: list[float],
        max_drawdown: float,
        n_matches: int,
        markets: list[str],
        calibration_data: dict[str, list[tuple[float, int]]],
        brier_data: dict[str, list[tuple[float, int]]],
        n_predictions: dict[str, int],
    ) -> BacktestResult:
        """Construit l'objet BacktestResult final."""
        initial = self.config.initial_bankroll
        total_pnl = final_bankroll - initial
        roi_pct = (total_pnl / initial) * 100 if initial > 0 else 0.0

        # Per-market summary
        per_market: dict[str, MarketBacktestSummary] = {}
        for m in markets:
            market_bets = [b for b in bets if b.market == m]
            n_pred = n_predictions.get(m, 0)
            if market_bets:
                wins = sum(1 for b in market_bets if b.outcome == 1)
                total_staked = sum(b.stake_amount for b in market_bets)
                total_pnl_m = sum(b.pnl for b in market_bets)
                avg_odds = np.mean([b.book_odds for b in market_bets])
                avg_edge = np.mean([b.edge for b in market_bets])
                avg_kelly = np.mean([b.kelly_stake_fraction for b in market_bets])
                roi_m = total_pnl_m / total_staked if total_staked > 0 else 0.0
                win_rate = wins / len(market_bets)
            else:
                wins = total_staked = total_pnl_m = avg_odds = 0.0
                avg_edge = avg_kelly = roi_m = win_rate = 0.0

            # Brier score sur toutes les prédictions du market (mode A)
            brier_pairs = brier_data.get(m, [])
            brier = None
            if brier_pairs:
                brier = float(np.mean([(p - o) ** 2 for p, o in brier_pairs]))

            per_market[m] = MarketBacktestSummary(
                market_name=m,
                total_predictions=n_pred,
                total_bets=len(market_bets),
                bet_rate=len(market_bets) / n_pred if n_pred else 0.0,
                wins=wins,
                win_rate=win_rate,
                avg_odds=float(avg_odds),
                total_staked=float(total_staked),
                total_pnl=float(total_pnl_m),
                roi=float(roi_m),
                brier_score=brier,
                avg_edge=float(avg_edge),
                avg_kelly=float(avg_kelly),
            )

        # Calibration buckets
        calibration = self._compute_calibration(calibration_data)

        # Sharpe (returns par match avec au moins un pari)
        if len(bankroll_curve) > 2:
            returns = np.diff(bankroll_curve) / np.array(bankroll_curve[:-1])
            sharpe = float(np.mean(returns) / np.std(returns) * np.sqrt(82)) \
                if np.std(returns) > 0 else 0.0  # 82 ≈ matchs/saison/équipe
        else:
            sharpe = 0.0

        return BacktestResult(
            config=asdict(self.config),
            initial_bankroll=initial,
            final_bankroll=final_bankroll,
            total_pnl=total_pnl,
            roi_pct=roi_pct,
            n_matches=n_matches,
            bets=bets,
            per_market=per_market,
            calibration=calibration,
            bankroll_curve=bankroll_curve,
            max_drawdown_pct=max_drawdown * 100,
            sharpe_ratio=sharpe,
        )

    def _compute_calibration(
        self,
        data: dict[str, list[tuple[float, int]]],
    ) -> dict[str, list[CalibrationBucket]]:
        """Calcule les buckets de calibration pour chaque marché."""
        result: dict[str, list[CalibrationBucket]] = {}
        buckets = self.config.calibration_buckets
        for market, pairs in data.items():
            if not pairs:
                continue
            buckets_for_market = []
            for i in range(len(buckets) - 1):
                low, high = buckets[i], buckets[i + 1]
                in_bucket = [(p, o) for p, o in pairs if low <= p < high]
                if not in_bucket:
                    continue
                n = len(in_bucket)
                n_wins = sum(o for _, o in in_bucket)
                avg_p = float(np.mean([p for p, _ in in_bucket]))
                actual = n_wins / n
                buckets_for_market.append(CalibrationBucket(
                    proba_low=low, proba_high=high,
                    n_predictions=n, n_wins=n_wins,
                    avg_proba_predicted=avg_p,
                    actual_win_rate=actual,
                    is_calibrated=abs(avg_p - actual) < 0.05,
                ))
            result[market] = buckets_for_market
        return result
