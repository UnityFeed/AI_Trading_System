"""
The strategy lab (see src/research/lab.py): about 200,000 combinations of
market filter x buy trigger x sell rule x trailing stop x core share,
tested on the full daily history with every CPU core, then judged:

1. how many beat holding in BOTH choosing eras (2013-16 and 2017-21), and
   whether those also do better on 2022-now than the rest (does choosing
   on the past help at all?)
2. the 25 best by the choosing score, with their 2022-now result
3. walk-forward 2017-now: each year chosen only on the years before, for
   three ways of choosing (single best, best family, top-10 average)
4. the common ground: which building blocks are in the good strategies,
   measured over ALL combinations, not just the winners
5. checks against luck: Deflated Sharpe of the best (N = every combination
   ever tried, from the trials ledger) and the probability of backtest
   overfitting (PBO) on a sample

Results of every combination: data/backtests/lab_results.csv. The run is
logged in the trials ledger. The database is only read. Takes a few
minutes (more on fewer CPU cores).

Usage:
    python -m scripts.run_strategy_lab
    python -m scripts.run_strategy_lab --fee 0.80        (Kraken, for comparison)
    python -m scripts.run_strategy_lab --workers 2
"""

import argparse
import csv
import math
import random
import time
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
from statistics import median

from src.analysis.market_data_quality import get_clean_candles
from src.analysis.primary_history import get_continuous_history
from src.app.routine import load_history
from src.backtesting.engine import CostSettings
from src.backtesting.exposure import run_exposure_backtest
from src.backtesting.ledger import daily_sharpes, log_trials, read_trials, trial_count
from src.backtesting.market import build_market
from src.backtesting.validation import deflated_sharpe, probability_of_overfitting
from src.data_collection.external_data import ExternalDataStore
from src.data_collection.market_data_repository import MarketDataRepository
from src.research import lab
from src.research.features import build_frame, coinbase_premium


OUTPUT = Path(__file__).resolve().parents[1] / "data" / "backtests" / "lab_results.csv"


def x(log_value: float) -> str:
    return f"x{math.exp(log_value):.2f}"


def load_premium(repository, history):
    """
    Coinbase premium per day over the Kraken/Bitstamp USD history (not the
    Bybit USDT prices, whose USDT/USD difference would distort it), leaving
    out hours that history took from Coinbase.
    """
    start, end = history.candles[0].timestamp, history.candles[-1].timestamp
    usd = get_continuous_history(repository=repository, start=start, end=end + timedelta(hours=1))
    coinbase = get_clean_candles(repository, "BTC/USD", "crypto", "1h", start, end, exchange="coinbase")
    own = [c for c in usd.candles if usd.sources.get(c.timestamp) != "coinbase"]
    return coinbase_premium(own, coinbase)


def daily_excess(market, spec, blocks, hold_daily, costs):
    """Daily strategy return minus holding's return, for one lab strategy."""
    filters, triggers, exits = blocks
    state = lab.holding_state(spec, [c.close for c in market.candles], filters, triggers, exits)
    result = run_exposure_backtest(market, range(len(market.candles)), lab.targets_for(spec, state),
                                   band=0.05, costs=costs, record_equity=True)
    values = {}
    for when, value in result.equity_curve:
        values[when.date()] = value
    days = sorted(values)
    return {d1: values[d1] / values[d0] - 1 - hold_daily[d1]
            for d0, d1 in zip(days, days[1:]) if d1 in hold_daily and values[d0] > 0}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fee", type=float, default=CostSettings().fee_pct)
    parser.add_argument("--slippage", type=float, default=CostSettings().slippage_pct)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--no-log", action="store_true")
    parser.add_argument("--db", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--external-db", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    started = time.time()
    costs = CostSettings(fee_pct=args.fee, slippage_pct=args.slippage)
    repository = MarketDataRepository(args.db) if args.db else MarketDataRepository()
    external = (ExternalDataStore(args.external_db) if args.external_db else ExternalDataStore()).load_all()
    history = load_history(repository)
    market = build_market(history, "1d", external=external)
    premium = load_premium(repository, history)
    frame = build_frame(market, premium)
    blocks = lab.building_blocks(frame)

    print("STRATEGY LAB: SYSTEMATIC SEARCH, CHOSEN ON 2013-2021 ONLY")
    print("========================================================")
    print(f"Costs per buy and per sell: fee {costs.fee_pct}% + slippage {costs.slippage_pct}%")
    print(f"Daily candles {market.candles[0].timestamp:%Y-%m-%d} to {market.candles[-1].timestamp:%Y-%m-%d}; "
          f"{len(frame.values)} features; Coinbase premium on {len(premium):,} days")
    print(f"Building blocks: {len(blocks[0])} filters, {len(blocks[1])} triggers, {len(blocks[2])} exits, "
          f"trailing stops {lab.TRAILS}, core shares {lab.CORES}")

    results, hold = lab.run_search(
        market, frame, costs, args.workers,
        progress=lambda done, total: print(f"  {done:,} / {total:,} tested ({time.time() - started:.0f} s)"),
    )
    n_specs = len(results)
    print(f"Tested {n_specs:,} combinations in {time.time() - started:.0f} s")
    print()

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        w = csv.writer(handle)
        w.writerow(["filter", "trigger", "exit", "trail", "core", "selection_score", "btc_vs_hold_2013_16",
                    "btc_vs_hold_2017_21", "btc_vs_hold_2022_now", "max_drawdown_pct", "exposure_pct",
                    "buys_2013_21", "buys_total"])
        for r in results:
            w.writerow([r.spec.filter, r.spec.trigger, r.spec.exit, r.spec.trail, r.spec.core,
                        round(r.selection_score, 4), round(math.exp(r.excess(lab.ERA_1)), 3),
                        round(math.exp(r.excess(lab.ERA_2)), 3), round(math.exp(r.test_excess), 3),
                        round(r.max_drawdown_pct, 1), round(r.exposure_pct, 1), r.buys_selection, r.buys_total])

    # 1. Does choosing on the past help?
    good = [r for r in lab.eligible(results) if r.selection_score > 0]
    rest = [r for r in lab.eligible(results) if r.selection_score <= 0]
    print("1. DOES CHOOSING ON 2013-2021 HELP ON 2022-NOW?")
    print(f"  eligible (>= {lab.MIN_TRADES_SELECTION} buys in 2013-21): {len(good) + len(rest):,}")
    for label, group in (("beat holding in BOTH eras", good), ("did not", rest)):
        if group:
            ahead = sum(r.test_excess > 0 for r in group) / len(group) * 100
            print(f"  {label:<28} {len(group):>7,}   ahead of holding 2022-now: {ahead:5.1f}%   "
                  f"median 2022-now {x(median(r.test_excess for r in group))}")
    print()

    # 2. Top by the choosing score
    top = lab.ranked(results)[:25]
    print("2. TOP 25 BY THE CHOOSING SCORE (weaker of 2013-16 and 2017-21), with 2022-now")
    print(f"  {'2013-16':>8}{'2017-21':>9}{'2022-now':>10}{'drop':>6}{'in BTC':>8}{'buys':>6}  strategy")
    for r in top:
        print(f"  {x(r.excess(lab.ERA_1)):>8}{x(r.excess(lab.ERA_2)):>9}{x(r.test_excess):>10}"
              f"{r.max_drawdown_pct:>5.0f}%{r.exposure_pct:>7.0f}%{r.buys_total:>6}  {r.spec.name}")
    if top:
        print(f"  top 25 ahead of holding 2022-now: {sum(r.test_excess > 0 for r in top)}/25")
    print()

    # 3. Walk-forward
    print("3. WALK-FORWARD 2017-NOW (each year picked on the years before it only)")
    for method, label in (("single", "single best"), ("family", "best family (median)"),
                          ("top10", "average of the top 10")):
        wf = lab.walk_forward(results, method)
        if not wf:
            continue
        total = sum(row.excess for row in wf)
        wins = sum(row.excess > 0 for row in wf)
        print(f"  {label:<24} BTC vs holding {x(total)} over {len(wf)} years, ahead in {wins}/{len(wf)} years")
        print("    " + "  ".join(f"{row.year}:{x(row.excess)}" for row in wf))
    wf = lab.walk_forward(results, "single")
    if wf:
        print("  picks (single best):")
        for row in wf:
            print(f"    {row.year}: {row.picks[0]}")
    print()

    # 4. Common ground over all combinations
    print("4. COMMON GROUND: building blocks over ALL eligible combinations")
    print("   (median choosing score / median 2022-now BTC vs holding / share ahead 2022-now)")
    pool = lab.eligible(results)
    for role in ("filter", "trigger", "exit", "trail", "core"):
        groups = defaultdict(list)
        for r in pool:
            groups[getattr(r.spec, role)].append(r)
        rows = sorted(groups.items(), key=lambda kv: median(r.selection_score for r in kv[1]), reverse=True)
        print(f"  {role.upper()} (best 8 of {len(rows)})")
        for key, group in rows[:8]:
            print(f"    {x(median(r.selection_score for r in group)):>7} {x(median(r.test_excess for r in group)):>7}"
                  f" {sum(r.test_excess > 0 for r in group) / len(group) * 100:5.0f}%  {key}  ({len(group):,})")
    print()

    # 5. Luck
    ledger = read_trials()
    n_trials = trial_count(ledger) + n_specs
    sharpes = [r.excess_sharpe for r in results]
    mean = sum(sharpes) / len(sharpes)
    variance = sum((s - mean) ** 2 for s in sharpes) / (len(sharpes) - 1)
    print("5. CHECKS AGAINST LUCK")
    print(f"  trials counted: {n_trials:,}")
    for r in top[:5]:
        series = list(daily_excess(market, r.spec, blocks, hold.daily, costs).values())
        dsr = deflated_sharpe(series, n_trials, variance)
        print(f"  Deflated Sharpe (beats holding, full history) {'-' if dsr is None else format(dsr, '.2f')}: {r.spec.name}")
    random.seed(7)
    sample = random.sample(pool, min(300, len(pool))) + top[:50]
    series = [daily_excess(market, r.spec, blocks, hold.daily, costs) for r in sample]
    days = sorted(set.intersection(*(set(s) for s in series)))
    pbo = probability_of_overfitting([[s[d] for s in series] for d in days])
    print(f"  PBO over {len(sample)} combinations ({len(days):,} days): {'-' if pbo is None else format(pbo, '.2f')}")
    print("  (0.5 or more: choosing the best is a coin flip; below 0.2: the ranking carries over)")
    print()

    if not args.no_log:
        best = top[0] if top else None
        log_trials([{
            "script": "run_strategy_lab", "timeframe": "1d", "n_trials": n_specs,
            "fee_pct": costs.fee_pct, "slippage_pct": costs.slippage_pct,
            "strategy": "best: " + best.spec.name if best else "",
            "btc_vs_hold": round(math.exp(best.test_excess), 3) if best else "",
            "note": "lab search; btc_vs_hold = best pick on 2022-now",
        }])
        print("Logged in the trials ledger.")
    print(f"All results: {OUTPUT}")
    print(f"Done in {time.time() - started:.0f} s. The database was only read.")


if __name__ == "__main__":
    main()
