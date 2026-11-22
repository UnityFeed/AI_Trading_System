"""
Market structure now (predictive engine, phase 1): for the weekly, daily and
4-hour chart, the current trend state, the last confirmed swing high and low
(what would have to break), the latest swings with their labels (HH/HL/LH/LL)
and the latest structure events (BOS / CHoCH / sweeps), plus how many of each
event happened per year on the daily chart.

The database is only read.

Usage:
    python -m scripts.run_market_structure
    python -m scripts.run_market_structure --left 5 --right 5   (bigger swings)
"""

import argparse
from collections import Counter
from pathlib import Path

from src.analysis.timeframes import aggregate_hourly_candles
from src.app.routine import load_history
from src.data_collection.market_data_repository import MarketDataRepository
from src.predictive_engine.structure import analyse


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--left", type=int, default=3)
    parser.add_argument("--right", type=int, default=3)
    parser.add_argument("--db", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    repository = MarketDataRepository(args.db) if args.db else MarketDataRepository()
    history = load_history(repository)

    print(f"MARKET STRUCTURE (swings need {args.left} candles before and {args.right} after;")
    print("a swing is only known after those later candles have closed)")
    print("=" * 72)
    for timeframe in ("1w", "1d", "4h"):
        candles = aggregate_hourly_candles(history.candles, timeframe).candles
        s = analyse(candles, timeframe, args.left, args.right)
        last = candles[-1]
        print(f"\n{timeframe}: {len(candles):,} candles, latest {last.timestamp:%Y-%m-%d %H:%M} close {last.close:,.0f}")
        print(f"  trend now: {s.trend[-1].upper()}   last swing high {s.swing_high[-1] or 0:,.0f}"
              f"   last swing low {s.swing_low[-1] or 0:,.0f}")
        print("  latest swings: " + ", ".join(
            f"{p.time:%Y-%m-%d} {p.kind} {p.price:,.0f}{' ' + p.label if p.label else ''}" for p in s.pivots[-6:]))
        print("  latest events: " + ", ".join(
            f"{e.time:%Y-%m-%d} {e.kind} {e.direction} @ {e.level:,.0f}" for e in s.events[-5:]))
        if timeframe == "1d":
            per_year = Counter((e.time.year, e.kind) for e in s.events)
            years = sorted({y for y, _ in per_year})
            print("  daily events per year (BOS / CHoCH / sweep): " + "  ".join(
                f"{y}: {per_year[(y, 'BOS')]}/{per_year[(y, 'CHoCH')]}/{per_year[(y, 'sweep')]}" for y in years))
    print("\nThe database was only read.")


if __name__ == "__main__":
    main()
