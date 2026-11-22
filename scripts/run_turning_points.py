"""
Turning points (see src/research/turning_points.py):

1. every swing low and high of 20% or more since 2013 (found with
   hindsight, only to study the past)
2. the lag: how many days after a low, and how many % above it, each
   registered strategy bought; how late and how far below a high it sold
3. what the market looked like just BEFORE lows and highs: for every
   feature, its average percentile rank in the 10 days up to a turn, and
   the lift: how much more often a low (or high) follows within 20 days
   when the feature is in its lowest or highest 10% than on an average day

The database is only read.

Usage:
    python -m scripts.run_turning_points
    python -m scripts.run_turning_points --threshold 0.30
"""

import argparse
from pathlib import Path
from statistics import median

from scripts.run_strategy_lab import load_premium
from src.app.routine import load_history
from src.backtesting.engine import CostSettings
from src.backtesting.exposure import MissingExternalData
from src.backtesting.market import build_market
from src.backtesting.report import prepare, run_strategy
from src.data_collection.external_data import ExternalDataStore
from src.data_collection.market_data_repository import MarketDataRepository
from src.research.features import build_frame
from src.research.turning_points import event_study, lag_study, zigzag
from src.strategies.registry import STRATEGIES


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=0.20, help="move that confirms a turn (0.20 = 20%%)")
    parser.add_argument("--db", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--external-db", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    repository = MarketDataRepository(args.db) if args.db else MarketDataRepository()
    external = (ExternalDataStore(args.external_db) if args.external_db else ExternalDataStore()).load_all()
    history = load_history(repository)
    market = build_market(history, "1d", external=external)
    frame = build_frame(market, load_premium(repository, history))
    closes = [c.close for c in market.candles]
    times = [c.timestamp for c in market.candles]
    turns = zigzag(closes, times, args.threshold)

    print(f"TURNING POINTS: swings of {args.threshold:.0%} or more (daily closes, found with hindsight)")
    print("=" * 72)
    lows = [t for t in turns if t.kind == "low"]
    highs = [t for t in turns if t.kind == "high"]
    print(f"{len(lows)} lows and {len(highs)} highs since {times[0]:%Y-%m-%d}")
    print("  " + ", ".join(f"{t.time:%Y-%m-%d} {t.kind} {t.price:,.0f}" for t in turns[-12:]))
    print()

    print("1. HOW LATE DO THE STRATEGIES ACT? (median over all their buys / sells)")
    print(f"  {'strategy':<36}{'buys':>5}{'days after low':>16}{'% above low':>13}"
          f"{'sells':>7}{'days after high':>17}{'% below high':>14}")
    for definition in STRATEGIES:
        try:
            result = run_strategy(market, definition, range(len(market.candles)), CostSettings(),
                                  prepared=prepare(market, definition))
        except MissingExternalData:
            continue
        actions = []
        if definition.kind == "rules":
            for t in result.trades:
                actions.append(("buy", t.entry_time, t.entry_price))
                if t.exit_reason != "end":
                    actions.append(("sell", t.exit_time, t.exit_price))
        else:
            for r in result.rebalances:
                actions.append(("buy" if r.to_weight > r.from_weight else "sell", r.time, r.price))
        rows = lag_study(turns, actions)
        buys = [r for r in rows if r.side == "buy"]
        sells = [r for r in rows if r.side == "sell"]

        def med(items, attr):
            return f"{median(getattr(r, attr) for r in items):.0f}" if items else "-"
        print(f"  {definition.name[:35]:<36}{len(buys):>5}{med(buys, 'days_late'):>16}{med(buys, 'pct_missed'):>12}%"
              f"{len(sells):>7}{med(sells, 'days_late'):>17}{med(sells, 'pct_missed'):>13}%")
    print("  (only actions within 180 days of a turn count; graded strategies count every share change)")
    print()

    evidence = event_study(frame, turns)
    print("2. WHAT HAPPENS JUST BEFORE A LOW? (sorted by lift)")
    print("   rank = average percentile in the 10 days up to the turn (0.5 = normal)")
    print("   lift = how much more often a low follows within 20 days when the feature is in its")
    print("          lowest 10% (<10%) or highest 10% (>90%), compared with an average day (1.0)")
    print(f"  {'feature':<30}{'rank before lows':>17}{'all days':>9}{'lift <10%':>10}{'lift >90%':>10}{'days':>7}")
    by_low = sorted(evidence, key=lambda e: max(e.low_lift_when_low or 0, e.low_lift_when_high or 0), reverse=True)
    for e in by_low[:15]:
        print(f"  {e.feature:<30}{e.rank_before_lows or 0:>17.2f}{e.rank_all_days or 0:>9.2f}"
              f"{e.low_lift_when_low or 0:>10.2f}{e.low_lift_when_high or 0:>10.2f}{e.days_low_extreme:>7}")
    print()
    print("3. WHAT HAPPENS JUST BEFORE A HIGH?")
    print(f"  {'feature':<30}{'rank before highs':>18}{'all days':>9}{'lift <10%':>10}{'lift >90%':>10}{'days':>7}")
    by_high = sorted(evidence, key=lambda e: max(e.high_lift_when_low or 0, e.high_lift_when_high or 0), reverse=True)
    for e in by_high[:15]:
        print(f"  {e.feature:<30}{e.rank_before_highs or 0:>18.2f}{e.rank_all_days or 0:>9.2f}"
              f"{e.high_lift_when_low or 0:>10.2f}{e.high_lift_when_high or 0:>10.2f}{e.days_high_extreme:>7}")
    print()
    print("Lift above ~2 on a few hundred days is a pattern worth testing; it is NOT a trading")
    print("rule yet: a turn is only known afterwards, and the lab/ML scripts test the timing.")
    print("The database was only read.")


if __name__ == "__main__":
    main()
