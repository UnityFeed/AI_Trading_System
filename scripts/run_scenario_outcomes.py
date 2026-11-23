"""
Scenario outcomes (predictive engine, phase 2): for every past day, did the
next H days end "bull" (a close reached +move first), "bear" (-move first)
or "range" (neither)? The move scales with that day's volatility (see
src/predictive_engine/outcomes.py).

Shows how often each happened overall, per year, and per market-structure
situation (daily and weekly trend), and the situation TODAY with the base
rates of comparable past days. These base rates are the yardstick every
scenario model (phase 3) has to beat.

The database is only read.

Usage:
    python -m scripts.run_scenario_outcomes
    python -m scripts.run_scenario_outcomes --horizon 14 --k 1.0
"""

import argparse
from collections import defaultdict
from pathlib import Path

from src.app.routine import load_history
from src.backtesting.market import build_market
from src.data_collection.market_data_repository import MarketDataRepository
from src.predictive_engine.outcomes import BaseRates, base_rates_by, outcomes
from src.predictive_engine.structure import analyse
from src.research.features import weekly_from_daily


def line(label: str, rates: BaseRates | None) -> str:
    if rates is None:
        return f"  {label:<34} no cases"
    d = rates.median_days
    return (f"  {label:<34} {rates.n:>6,} days   bull {rates.bull:5.1%}  bear {rates.bear:5.1%}  "
            f"range {rates.range:5.1%}   median days to decide: bull {d['bull'] or '-'}, bear {d['bear'] or '-'}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=30, help="days ahead (default 30)")
    parser.add_argument("--k", type=float, default=1.0, help="barrier = k x typical move over the horizon")
    parser.add_argument("--db", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    repository = MarketDataRepository(args.db) if args.db else MarketDataRepository()
    history = load_history(repository)
    market = build_market(history, "1d")
    out = outcomes(market, args.horizon, args.k)
    candles = market.candles

    daily = analyse(candles, "1d").trend
    weekly_candles = weekly_from_daily(candles)
    weekly = analyse(weekly_candles, "1w").trend
    # weekly trend known on each day (completed weeks only)
    from datetime import timedelta
    weekly_on_day, k = [], -1
    for c in candles:
        close = c.timestamp + timedelta(days=1)
        while k + 1 < len(weekly_candles) and weekly_candles[k + 1].timestamp + timedelta(days=7) <= close:
            k += 1
        weekly_on_day.append(weekly[k] if k >= 0 else None)

    known = [o for o in out if o is not None]
    print(f"SCENARIO OUTCOMES: next {args.horizon} days, barriers at {args.k} x typical move "
          f"(median {sorted(o.move_pct for o in known)[len(known) // 2]:.1f}%)")
    print("=" * 96)
    print(line("all days", BaseRates.of(known)))
    print()
    print("By year:")
    per_year = defaultdict(list)
    for o in known:
        per_year[candles[o.index].timestamp.year].append(o)
    for year in sorted(per_year):
        print(line(str(year), BaseRates.of(per_year[year])))
    print()
    print("By market structure (known at each day's close):")
    for label, groups in (("daily trend", daily), ("weekly trend", weekly_on_day)):
        rates = base_rates_by(out, groups)
        for value in ("up", "down", "none"):
            print(line(f"{label} {value}", rates.get(value)))
    combined = base_rates_by(out, [f"{d}/{w}" for d, w in zip(daily, weekly_on_day)])
    print()
    print("Daily / weekly trend together:")
    for key in sorted(combined):
        print(line(f"daily {key.split('/')[0]}, weekly {key.split('/')[1]}", combined[key]))

    today = len(candles) - 1
    key = f"{daily[today]}/{weekly_on_day[today]}"
    print()
    print(f"TODAY ({candles[today].timestamp:%Y-%m-%d}, close {candles[today].close:,.0f}): daily trend "
          f"{daily[today]}, weekly trend {weekly_on_day[today]}")
    print(line("past days in the same situation", combined.get(key)))
    print("  These are base rates (how often it happened before), not a forecast yet:")
    print("  phase 3 must beat them on years it did not learn from.")
    print("\nThe database was only read.")


if __name__ == "__main__":
    main()
