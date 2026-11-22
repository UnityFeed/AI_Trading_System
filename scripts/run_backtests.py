"""
Backtest every long-only indicator combination on the continuous history
and report which ones hold up on real data.

For each timeframe (1h, 4h, 1d):
1. Buy-and-hold in each window (the benchmark to beat).
2. The 10 combinations that did best in BOTH selection windows
   (bitstamp era 2013-2016 and kraken era 2017-2021), judged by their
   weakest window, and how they then did on the unseen years (2022-now).
3. Building blocks: for each indicator rule, the median result of all
   combinations that use it. Rules that help across many combinations,
   in every window, are the "common ground"; a single lucky combination
   is not.

Full results are written to data/backtests/ (one CSV per timeframe) for
opening in Excel. The database is only read.

Usage:
    python -m scripts.run_backtests                 (Kraken Pro taker fee 0.80%)
    python -m scripts.run_backtests --fee 0.40      (maker / limit-order fee)
    python -m scripts.run_backtests --timeframes 4h 1d
"""

import argparse
import csv
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

from src.analysis.primary_history import get_continuous_history
from src.backtesting.engine import CostSettings
from src.backtesting.market import build_market
from src.backtesting.search import (
    SELECTION_WINDOWS,
    TEST_WINDOW,
    WINDOWS,
    benchmark,
    rank_by_selection,
    search,
)
from src.backtesting.ledger import log_trials
from src.backtesting.search import all_specs
from src.data_collection.market_data_repository import MarketDataRepository


HISTORY_START = datetime(2013, 1, 1, tzinfo=timezone.utc)
MIN_TRADES = {"1h": 10, "4h": 5, "1d": 3}
TOP_N = 10
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "backtests"


def line(result) -> str:
    return (
        f"return {result.total_return_pct:>+9.1f}%  "
        f"yearly {result.cagr_pct:>+6.1f}%  "
        f"max drop {result.max_drawdown_pct:>5.1f}%  "
        f"trades {len(result.trades):>4}  "
        f"wins {result.win_rate_pct:>3.0f}%  "
        f"in market {result.exposure_pct:>3.0f}%"
    )


def write_csv(path: Path, scores, min_trades: int) -> None:

    path.parent.mkdir(parents=True, exist_ok=True)
    windows = [name for name, _, _ in WINDOWS]

    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        header = ["strategy", "trend", "trigger", "volume", "exit", "stop_atr",
                  "selection_score"]
        for w in windows:
            header += [f"{w} return %", f"{w} yearly %", f"{w} max drop %",
                       f"{w} trades", f"{w} win %", f"{w} calmar"]
        writer.writerow(header)

        for score in scores:
            s = score.spec
            selection = score.selection_score(min_trades)
            row = [s.name, s.trend, s.trigger, s.volume, s.exit, s.stop_atr or "",
                   "" if selection is None else round(selection, 3)]
            for w in windows:
                r = score.results.get(w)
                row += ([""] * 6 if r is None else [
                    round(r.total_return_pct, 2), round(r.cagr_pct, 2),
                    round(r.max_drawdown_pct, 2), len(r.trades),
                    round(r.win_rate_pct, 1), round(r.calmar, 3)])
            writer.writerow(row)


def building_blocks(scores, bench, min_trades: int) -> None:

    print("BUILDING BLOCKS (median over every combination that uses the rule)")
    print("  calmar = yearly return / max drop; higher is better.")
    windows = [name for name, _, _ in WINDOWS if name in bench]
    print(
        "  " + f"{'rule':<26}" + "".join(f"{w:>15}" for w in windows)
        + f"{'beats B&H*':>12}"
    )
    print(
        "  " + f"{'buy & hold':<26}"
        + "".join(f"{bench[w].calmar:>15.2f}" for w in windows)
    )

    for role in ("trend", "trigger", "volume", "exit", "stop_atr"):
        values = sorted({getattr(s.spec, role) for s in scores}, key=str)
        for value in values:
            group = [
                s for s in scores
                if getattr(s.spec, role) == value
                and all(len(s.results[w].trades) >= min_trades for w in SELECTION_WINDOWS)
            ]
            if not group:
                continue
            medians = [median(s.results[w].calmar for s in group) for w in windows]
            beats = sum(
                all(s.results[w].calmar > bench[w].calmar for w in windows)
                for s in group
            )
            label = f"{role}: {value if value is not None else 'no stop'}"
            print(
                "  " + f"{label:<26}" + "".join(f"{m:>15.2f}" for m in medians)
                + f"{beats:>6}/{len(group):<5}"
            )
    print("  * combinations whose calmar beats buy & hold in every window")
    print()


def report_timeframe(history, timeframe: str, costs: CostSettings, fee_label: str) -> None:

    started = time.time()
    market = build_market(history, timeframe)
    bench = benchmark(market, costs)
    scores = search(market, costs)
    min_trades = MIN_TRADES[timeframe]

    title = f"TIMEFRAME {timeframe}  ({len(market.candles):,} candles, {len(scores)} combinations)"
    print(title)
    print("=" * len(title))
    print("Buy & hold:")
    for name, result in bench.items():
        print(f"  {name:<13} {line(result)}  calmar {result.calmar:.2f}")
    print()

    ranked = rank_by_selection(scores, min_trades)
    eligible = len(ranked)
    print(
        f"Combinations with at least {min_trades} trades in both selection "
        f"windows: {eligible} of {len(scores)}"
    )
    print()

    print(f"TOP {TOP_N}, chosen on 2013-2021 only (weakest-window calmar):")
    for position, (value, score) in enumerate(ranked[:TOP_N], start=1):
        print(f"{position:>2}. {score.spec.name}   [score {value:.2f}]")
        for name, result in score.results.items():
            marker = "  <- unseen" if name == TEST_WINDOW else ""
            print(f"      {name:<13} {line(result)}  calmar {result.calmar:>5.2f}{marker}")
    print()

    if TEST_WINDOW in bench and ranked:
        test_bench = bench[TEST_WINDOW]
        top = [score for _, score in ranked[:TOP_N]]
        everyone = [score for _, score in ranked]

        def share_beating(group, attribute):
            wins = sum(
                getattr(s.results[TEST_WINDOW], attribute) > getattr(test_bench, attribute)
                for s in group
            )
            return f"{wins}/{len(group)}"

        print("UNSEEN YEARS (2022-now): did choosing on the past help?")
        print(
            f"  median calmar   top {TOP_N}: "
            f"{median(s.results[TEST_WINDOW].calmar for s in top):.2f}   "
            f"all eligible: {median(s.results[TEST_WINDOW].calmar for s in everyone):.2f}   "
            f"buy & hold: {test_bench.calmar:.2f}"
        )
        print(
            f"  beat buy & hold on calmar: top {TOP_N} {share_beating(top, 'calmar')}, "
            f"all {share_beating(everyone, 'calmar')}"
        )
        print(
            f"  beat buy & hold on return: top {TOP_N} {share_beating(top, 'total_return_pct')}, "
            f"all {share_beating(everyone, 'total_return_pct')}"
        )
        print()

    building_blocks(scores, bench, min_trades)

    path = OUTPUT_DIR / f"backtest_{timeframe}_fee{fee_label}.csv"
    write_csv(path, scores, min_trades)
    print(f"All {len(scores)} results saved to {path}")
    print(f"({time.time() - started:.0f} s)")
    print()


def main() -> None:

    parser = argparse.ArgumentParser()
    parser.add_argument("--fee", type=float, default=CostSettings().fee_pct,
                        help="fee per buy or sell, in percent (default 0.80)")
    parser.add_argument("--slippage", type=float, default=CostSettings().slippage_pct,
                        help="slippage per buy or sell, in percent (default 0.05)")
    parser.add_argument("--timeframes", nargs="+", default=["1h", "4h", "1d"],
                        choices=["1h", "4h", "1d"])
    parser.add_argument("--db", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    costs = CostSettings(fee_pct=args.fee, slippage_pct=args.slippage)
    repository = MarketDataRepository(args.db) if args.db else MarketDataRepository()
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    history = get_continuous_history(repository=repository, start=HISTORY_START, end=end)

    print("LONG-ONLY STRATEGY BACKTEST (buy low, sell high; no margin)")
    print("===========================================================")
    print(f"Costs per buy and per sell: fee {costs.fee_pct}% + slippage {costs.slippage_pct}%")
    print("Signals at a candle's close, orders filled at the next open;")
    print("never on hours filled in from another exchange or at Kraken's")
    print("reopening print. Selection uses 2013-2021 only; 2022-now is unseen.")
    print()

    for timeframe in args.timeframes:
        report_timeframe(history, timeframe, costs, f"{costs.fee_pct:g}")

    # Trials ledger: these combinations count as tried (for the Deflated Sharpe Ratio).
    log_trials([
        {"script": "run_backtests", "timeframe": timeframe, "n_trials": len(all_specs()),
          "fee_pct": costs.fee_pct, "slippage_pct": costs.slippage_pct,
          "note": "strategy search: every combination, chosen on 2013-2021"}
        for timeframe in args.timeframes
    ])
    print("Logged in the trials ledger (data/backtests/trials.csv).")

    print("Backtest complete. The database was only read.")


if __name__ == "__main__":
    main()
