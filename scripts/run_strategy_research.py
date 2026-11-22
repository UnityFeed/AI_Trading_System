"""
Strategy research (roadmap 9b/9c): every strategy in the registry, tested
the same way, with the checks against luck from the research report.

For each strategy (all on the full continuous history, Kraken fees):
- total result, BTC compared with holding, worst drop, Sharpe, Sortino,
  share of the 20 best BTC days captured, turnover, break-even fee,
  the exposure-matched benchmark (fixed mix with the same average BTC share)
- the three eras: 2013-2016, 2017-2021, 2022-now (vs buy-and-hold)
- how many "1 January" start years end with more BTC than holding
- how the result changes with the fee (0.10 / 0.25 / 0.40 / 0.80%)
- Deflated Sharpe Ratio: is the Sharpe higher than the best of N random
  tries would reach by luck? N = every trial in the ledger + this run
- PBO: how often the strategy that looks best on half the history ends in
  the bottom half on the other half

Every strategy tested is logged in the trials ledger
(data/backtests/trials.csv). The database is only read.

Usage:
    python -m scripts.run_strategy_research
    python -m scripts.run_strategy_research --fee 0.40
    python -m scripts.run_strategy_research --no-log      (do not write the ledger)
"""

import argparse
import time
from datetime import datetime, timezone
from pathlib import Path

from src.app.routine import load_history
from src.backtesting.engine import CostSettings, buy_and_hold
from src.backtesting.exposure import MissingExternalData
from src.backtesting.ledger import daily_sharpes, log_trials, read_trials, trial_count
from src.backtesting.market import build_market
from src.backtesting.metrics import daily_returns
from src.backtesting.report import END_OF_DATA, btc_vs_hold, prepare, run_strategy, strategy_report
from src.backtesting.validation import daily_sharpe, deflated_sharpe, probability_of_overfitting
from src.data_collection.external_data import ExternalDataStore
from src.data_collection.market_data_repository import MarketDataRepository
from src.strategies.registry import STRATEGIES


ERAS = (
    ("2013-16", datetime(2013, 1, 1, tzinfo=timezone.utc), datetime(2017, 1, 1, tzinfo=timezone.utc)),
    ("2017-21", datetime(2017, 1, 1, tzinfo=timezone.utc), datetime(2022, 1, 1, tzinfo=timezone.utc)),
    ("2022-now", datetime(2022, 1, 1, tzinfo=timezone.utc), END_OF_DATA),
)
FEE_LEVELS = (0.10, 0.25, 0.40, 0.80)


def pct(value) -> str:
    return "-" if value is None else f"{value:+,.0f}%"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fee", type=float, default=CostSettings().fee_pct)
    parser.add_argument("--slippage", type=float, default=CostSettings().slippage_pct)
    parser.add_argument("--no-log", action="store_true", help="do not write the trials ledger")
    parser.add_argument("--db", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--external-db", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    started = time.time()
    costs = CostSettings(fee_pct=args.fee, slippage_pct=args.slippage)
    repository = MarketDataRepository(args.db) if args.db else MarketDataRepository()
    external = (ExternalDataStore(args.external_db) if args.external_db else ExternalDataStore()).load_all()
    history = load_history(repository)
    markets = {}

    def market_for(timeframe):
        if timeframe not in markets:
            markets[timeframe] = build_market(history, timeframe, external=external)
        return markets[timeframe]

    print("STRATEGY RESEARCH: EVERY REGISTERED STRATEGY, SAME TEST")
    print("=======================================================")
    print(f"Costs per buy and per sell: fee {costs.fee_pct}% + slippage {costs.slippage_pct}%")
    print("Full continuous history, next-open fills, no fills on substituted hours.")
    print("External data: " + ", ".join(f"{k} {len(v):,} days" for k, v in external.items()))
    print()

    rows = []
    for definition in STRATEGIES:
        market = market_for(definition.timeframe)
        try:
            report = strategy_report(market, definition, costs)
        except MissingExternalData as error:
            print(f"  skipped {definition.id}: {error}")
            continue
        prepared = prepare(market, definition)
        full = range(len(market.candles))
        result = run_strategy(market, definition, full, costs, record_equity=True, prepared=prepared)
        eras = {}
        for name, start, end in ERAS:
            window = market.index_range(start, end)
            if len(window) < 2:
                continue
            r = run_strategy(market, definition, window, costs, prepared=prepared)
            h = buy_and_hold(market, window, costs)
            eras[name] = (r.total_return_pct, h.total_return_pct, btc_vs_hold(r, h))
        fees = {}
        for fee in FEE_LEVELS:
            c = CostSettings(fee_pct=fee, slippage_pct=costs.slippage_pct)
            fees[fee] = btc_vs_hold(run_strategy(market, definition, full, c, prepared=prepared),
                                    buy_and_hold(market, full, c))
        rows.append({
            "definition": definition, "report": report, "eras": eras, "fees": fees,
            "returns": dict(daily_returns(result.equity_curve)),
        })

    if not rows:
        print("Nothing to test.")
        return

    # 1. Main table
    print("1. FULL HISTORY")
    print(f"{'strategy':<34}{'total':>10}{'vs hold':>9}{'drop':>7}{'Sharpe':>8}{'Sortino':>8}"
          f"{'top20':>7}{'trade/y':>8}{'BE fee':>8}{'vs mix':>8}{'starts':>8}")
    held = rows[0]["report"]
    hm = held["buy_and_hold_metrics"]
    print(f"{'Buy and hold':<34}{pct(held['buy_and_hold']['total_return_pct']):>10}{'x1.00':>9}"
          f"{held['buy_and_hold']['max_drawdown_pct']:>6.0f}%{hm['sharpe']:>8.2f}{hm['sortino']:>8.2f}"
          f"{'100%':>7}")
    for row in rows:
        r, d = row["report"], row["definition"]
        s, m, mix = r["summary"], r["metrics"], r["exposure_matched"]
        ahead = sum(x["btc_vs_hold"] >= 1 for x in r["by_start_year"])
        be = m["break_even_fee_pct"]
        print(f"{d.name[:33]:<34}{pct(s['total_return_pct']):>10}{'x' + format(s['btc_vs_hold'], '.2f'):>9}"
              f"{s['max_drawdown_pct']:>6.0f}%{m['sharpe']:>8.2f}{m['sortino']:>8.2f}"
              f"{(format(m['top20_capture_pct'], '.0f') + '%') if m['top20_capture_pct'] is not None else '-':>7}"
              f"{(format(m['turnover_per_year'] * 100, '.0f') + '%') if m['turnover_per_year'] is not None else '-':>8}"
              f"{'never' if be is None else (format(be, '.2f') + '%'):>8}"
              f"{('x' + format(mix['strategy_vs_mix'], '.2f')) if mix and mix['strategy_vs_mix'] else '-':>8}"
              f"{str(ahead) + '/' + str(len(r['by_start_year'])):>8}")
    print("  vs hold: end value / buy-and-hold end value (BTC compared with holding)")
    print("  top20: share of the gain on BTC's 20 best days the strategy also made")
    print("  trade/y: value traded per year as a share of the account (buy + sell of everything = 200%)")
    print("  BE fee: fee per side at which it would end level with holding ('never': not even at 0%)")
    print("  vs mix: compared with a fixed BTC/cash mix holding the same average share of BTC")
    print("  starts: '1 January' start years that end with at least as much BTC as holding")
    print()

    # 2. Eras
    print("2. BY ERA (each starts with cash): strategy / buy and hold -> BTC vs holding")
    print(f"{'strategy':<34}" + "".join(f"{name:>28}" for name, _, _ in ERAS))
    for row in rows:
        cells = []
        for name, _, _ in ERAS:
            era = row["eras"].get(name)
            cells.append("-" if era is None else f"{pct(era[0])} / {pct(era[1])} x{era[2]:.2f}")
        print(f"{row['definition'].name[:33]:<34}" + "".join(f"{c:>28}" for c in cells))
    print()

    # 3. Fees
    print("3. FEE SENSITIVITY: BTC compared with holding, full history")
    print(f"{'strategy':<34}" + "".join(f"{f'{fee:.2f}%':>9}" for fee in FEE_LEVELS))
    for row in rows:
        print(f"{row['definition'].name[:33]:<34}" + "".join(f"{'x' + format(row['fees'][fee], '.2f'):>9}" for fee in FEE_LEVELS))
    print("  Bybit EU (your account): 0.25%; Bybit global 0.10%; Kraken Pro 0.80% taker / 0.40% maker.")
    print()

    # 4. Luck checks
    ledger = read_trials()
    previous = trial_count(ledger)
    n_trials = previous + len(rows)
    sharpe_by_strategy = {row["definition"].id: daily_sharpe(list(row["returns"].values())) for row in rows}
    sample = list(sharpe_by_strategy.values()) + daily_sharpes(ledger)
    mean = sum(sample) / len(sample)
    variance = sum((x - mean) ** 2 for x in sample) / (len(sample) - 1) if len(sample) > 1 else 0.0
    print("4. CHECKS AGAINST LUCK")
    print(f"  Trials counted: {n_trials:,} ({previous:,} in the ledger before this run + {len(rows)} now)")
    common = sorted(set.intersection(*(set(row["returns"]) for row in rows)))
    hold_returns = dict(daily_returns(buy_and_hold(market_for("1d"), range(len(market_for("1d").candles)),
                                                   costs, record_equity=True).equity_curve))
    common = [day for day in common if day in hold_returns]
    excess = {
        row["definition"].id: [row["returns"][day] - hold_returns[day] for day in common] for row in rows
    }
    excess_sharpes = [daily_sharpe(values) for values in excess.values()]
    excess_mean = sum(excess_sharpes) / len(excess_sharpes)
    excess_variance = (
        sum((x - excess_mean) ** 2 for x in excess_sharpes) / (len(excess_sharpes) - 1)
        if len(excess_sharpes) > 1 else 0.0
    )
    print("  Deflated Sharpe Ratio: probability the result is real after N trials (> 0.95 = convincing)")
    print(f"    {'':<42}{'Sharpe > 0':>12}{'beats holding':>15}")
    for row in rows:
        dsr = deflated_sharpe(list(row["returns"].values()), n_trials, variance)
        dsr_excess = deflated_sharpe(excess[row["definition"].id], n_trials, excess_variance)
        print(f"    {row['definition'].name[:40]:<42}{'-' if dsr is None else format(dsr, '.2f'):>12}"
              f"{'-' if dsr_excess is None else format(dsr_excess, '.2f'):>15}")
    print("    'Sharpe > 0' is easy for anything that holds BTC in a 13-year bull market;")
    print("    'beats holding' tests the daily return above buy-and-hold, which is what matters.")
    matrix = [[row["returns"][day] for row in rows] for day in common]
    pbo = probability_of_overfitting(matrix)
    print(f"  PBO across these {len(rows)} strategies ({len(common):,} common days, 16 blocks): "
          f"{'-' if pbo is None else format(pbo, '.2f')}")
    print("    (0.5 or more: picking the best of them is no better than a coin flip; below 0.2: the ranking carries over)")
    print()

    if not args.no_log:
        log_trials([
            {
                "script": "run_strategy_research", "strategy": row["definition"].id,
                "timeframe": row["definition"].timeframe, "rules": row["definition"].rules_text,
                "fee_pct": costs.fee_pct, "slippage_pct": costs.slippage_pct,
                "start": row["report"]["summary"]["start"][:10], "end": row["report"]["summary"]["end"][:10],
                "total_return_pct": row["report"]["summary"]["total_return_pct"],
                "cagr_pct": row["report"]["summary"]["yearly_pct"],
                "max_drawdown_pct": row["report"]["summary"]["max_drawdown_pct"],
                "daily_sharpe": round(sharpe_by_strategy[row["definition"].id], 6),
                "sharpe": row["report"]["metrics"]["sharpe"],
                "btc_vs_hold": row["report"]["summary"]["btc_vs_hold"],
                "note": "registered strategy, full history",
            }
            for row in rows
        ])
        print("Logged in the trials ledger (data/backtests/trials.csv).")
    print(f"Done in {time.time() - started:.0f} s. The database was only read.")


if __name__ == "__main__":
    main()
