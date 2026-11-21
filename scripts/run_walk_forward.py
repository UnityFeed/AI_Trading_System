"""
Full-history test of the long-only strategies (roadmap step 5c).

Every combination is run once over the whole history (2013 to now). Then:

A. The candidate strategies found in step 5a, year by year next to
   buy-and-hold: do they win steadily, or only in one year?

B. Walk-forward: for every year from 2016 on, pick the combination that
   did best on all the years BEFORE it, and see how that pick did in the
   year itself. Chained together this is one honest result over the full
   history: no pick ever used the year it is judged on.

The database is only read.

Usage:
    python -m scripts.run_walk_forward                  (fee 0.80%, 1d 4h 1h)
    python -m scripts.run_walk_forward --fee 0.40
    python -m scripts.run_walk_forward --timeframes 1d
"""

import argparse
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from src.analysis.primary_history import get_continuous_history
from src.backtesting.conditions import evaluate_all
from src.backtesting.engine import CostSettings, buy_and_hold, run_backtest
from src.backtesting.market import build_market
from src.backtesting.search import StrategySpec, all_specs
from src.backtesting.walk_forward import (
    chain_returns,
    curve_stats,
    stitched_curve,
    summarize,
    walk_forward,
)
from src.data_collection.market_data_repository import MarketDataRepository


HISTORY_START = datetime(2013, 1, 1, tzinfo=timezone.utc)
FIRST_TEST_YEAR = 2016
MIN_TRADES_PER_YEAR = {"1h": 2.5, "4h": 1.25, "1d": 0.75}

# Best daily candidates from the step 5a run on the owner's real database.
CANDIDATES = (
    StrategySpec("ema50>ema200", "macd_cross_up", "none", "ema20_cross_down_ema50", 2.0),
    StrategySpec("close>ema200", "ema20_cross_up_ema50", "none", "ema20_cross_down_ema50", 2.0),
    StrategySpec("ema50>ema200", "rsi<40", "none", "ema20_cross_down_ema50", None),
)


def entry_exit(blocks, spec: StrategySpec):
    entry = [
        a and b and c for a, b, c in zip(
            blocks["trend"][spec.trend],
            blocks["trigger"][spec.trigger],
            blocks["volume"][spec.volume],
        )
    ]
    return entry, blocks["exit"][spec.exit]


def run_full(market, blocks, spec, costs):
    entry, exit_signal = entry_exit(blocks, spec)
    return run_backtest(
        market, range(len(market.candles)), entry, exit_signal,
        spec.stop_atr, costs, record_equity=True,
    )


def pct(value: float) -> str:
    return f"{value:>+8.1f}%"


def report_timeframe(history, timeframe: str, costs: CostSettings) -> None:

    started = time.time()
    market = build_market(history, timeframe)
    blocks = evaluate_all(market)
    full_range = range(len(market.candles))

    bench_run = buy_and_hold(market, full_range, costs, record_equity=True)
    bench = summarize(bench_run)

    summaries = {}
    for spec in all_specs():
        summaries[spec] = summarize(run_full(market, blocks, spec, costs))

    years = sorted(bench.years)

    title = f"TIMEFRAME {timeframe}  ({len(market.candles):,} candles, {len(summaries)} combinations)"
    print(title)
    print("=" * len(title))

    # A. Candidates year by year -------------------------------------------
    print("A. CANDIDATES FROM STEP 5a, YEAR BY YEAR (return in the year / worst drop)")
    header = f"   {'year':<6}{'buy & hold':>22}"
    for n in range(1, len(CANDIDATES) + 1):
        header += f"{'candidate ' + str(n):>26}"
    print(header)

    for year in years:
        held = bench.years[year]
        line = f"   {year:<6}{pct(held.return_pct)} / {held.max_drawdown_pct:>5.1f}%    "
        for spec in CANDIDATES:
            stats = summaries[spec].years.get(year)
            line += (
                f"{pct(stats.return_pct)} / {stats.max_drawdown_pct:>5.1f}% {stats.trades:>2}t  "
                if stats else f"{'-':>26}"
            )
        print(line)

    last_year = years[-1]
    held_all = bench.to_year_end[last_year]
    print(
        f"   whole history: buy & hold {pct(held_all.return_pct)}, "
        f"worst drop {held_all.max_drawdown_pct:.1f}%"
    )
    for n, spec in enumerate(CANDIDATES, start=1):
        total = summaries[spec].to_year_end[last_year]
        beaten = sum(
            summaries[spec].years[y].return_pct > bench.years[y].return_pct
            for y in years if y in summaries[spec].years
        )
        print(
            f"   candidate {n}: {pct(total.return_pct)}, worst drop "
            f"{total.max_drawdown_pct:.1f}%, {total.trades} trades, "
            f"beat buy & hold in {beaten}/{len(years)} years  -- {spec.name}"
        )
    print()

    # B. Walk-forward ------------------------------------------------------
    test_years = [y for y in years if y >= FIRST_TEST_YEAR]
    picks = walk_forward(summaries, bench, test_years, MIN_TRADES_PER_YEAR[timeframe])

    print("B. WALK-FORWARD: each year's pick is chosen on the years before it only")
    print(f"   {'year':<6}{'pick':>10}{'buy & hold':>12}{'pick drop':>11}{'B&H drop':>10}  chosen combination")
    for pick in picks:
        print(
            f"   {pick.year:<6}{pct(pick.strategy.return_pct):>10}{pct(pick.buy_and_hold.return_pct):>12}"
            f"{pick.strategy.max_drawdown_pct:>10.1f}%{pick.buy_and_hold.max_drawdown_pct:>9.1f}%  "
            f"{pick.spec.name}"
        )

    if picks:
        full_runs = {
            spec: run_full(market, blocks, spec, costs)
            for spec in {pick.spec for pick in picks}
        }
        stitched = stitched_curve(picks, full_runs)
        stitched_stats = curve_stats(stitched, stitched[0][0], datetime.max.replace(tzinfo=timezone.utc), 0)
        held_span = curve_stats(
            bench_run.equity_curve, stitched[0][0],
            datetime.max.replace(tzinfo=timezone.utc), 0,
        )

        print()
        print(f"   {picks[0].year}-{picks[-1].year} chained:")
        print(
            f"     walk-forward picks: total {pct(chain_returns([p.strategy for p in picks]))}, "
            f"worst drop {stitched_stats.max_drawdown_pct:.1f}%"
        )
        print(
            f"     buy & hold:         total {pct(held_span.return_pct)}, "
            f"worst drop {held_span.max_drawdown_pct:.1f}%"
        )
        wins = sum(p.strategy.return_pct > p.buy_and_hold.return_pct for p in picks)
        print(f"     pick beat buy & hold in {wins}/{len(picks)} years")
        common = Counter(p.spec.name for p in picks).most_common(3)
        print("     most chosen:")
        for name, count in common:
            print(f"       {count}x {name}")

    print(f"   ({time.time() - started:.0f} s)")
    print()


def main() -> None:

    parser = argparse.ArgumentParser()
    parser.add_argument("--fee", type=float, default=CostSettings().fee_pct)
    parser.add_argument("--slippage", type=float, default=CostSettings().slippage_pct)
    parser.add_argument("--timeframes", nargs="+", default=["1d", "4h", "1h"],
                        choices=["1h", "4h", "1d"])
    parser.add_argument("--db", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    costs = CostSettings(fee_pct=args.fee, slippage_pct=args.slippage)
    repository = MarketDataRepository(args.db) if args.db else MarketDataRepository()
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    history = get_continuous_history(repository=repository, start=HISTORY_START, end=end)

    print("FULL-HISTORY TEST: YEAR BY YEAR AND WALK-FORWARD")
    print("=================================================")
    print(f"Costs per buy and per sell: fee {costs.fee_pct}% + slippage {costs.slippage_pct}%")
    print("Long-only, all-in/all-out. Each strategy runs once over 2013-now;")
    print("years are read from that single run (positions carry over year ends).")
    print()

    for timeframe in args.timeframes:
        report_timeframe(history, timeframe, costs)

    print("Test complete. The database was only read.")


if __name__ == "__main__":
    main()
