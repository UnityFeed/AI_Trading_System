"""
TRAINING SESSION for the learning engine ("the AI") on 1h, 4h and 1d.

For each timeframe and horizon it replays the whole chart candle by candle
with 10 setting versions, then:
  - honest result: each year uses the version that scored best on the EARLIER
    years only (nested walk-forward); this is what the app shows and logs;
  - memorised passes: the version used now goes over the same chart again
    (twice by default), starting with everything it already learned. These
    scores are inflated by memory; they show how much, nothing more.
The 1h and 4h learners also read the higher timeframes (4h, 1d, 1w: trend,
trend strength, distance from EMA 50/200, RSI, MACD of the last COMPLETED
higher candle).

Saves data/predictive/engine_cache.pkl (the app loads it, so it starts with
the trained forecasts) and data/predictive/forecasts_<tf>_h<horizon>.csv
(every forecast as it was made, with its outcome). The databases are only read.

Usage (about 5-15 minutes on 4 cores):
    python -m scripts.train_engine
    python -m scripts.train_engine --timeframes 1d 4h --workers 2 --memorised 1
"""

import argparse
import os
import time
from pathlib import Path

from src.analysis.technical_indicators import indicator_tables
from src.app.routine import load_history
from src.data_collection.external_data import ExternalDataStore
from src.data_collection.market_data_repository import MarketDataRepository
from src.data_collection.other_markets import OtherMarketsStore
from src.predictive_engine import learner, training
from src.research import other_market_features
from src.predictive_engine.service import EngineService, horizon_label


def pct(x) -> str:
    return "-" if x is None else f"{x:+.2%}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeframes", nargs="+", default=list(training.TIMEFRAMES), choices=training.TIMEFRAMES)
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--memorised", type=int, default=2, help="extra passes over the full chart (reported only)")
    parser.add_argument("--markets", choices=other_market_features.MODES, default=other_market_features.AI_MODE,
                        help="use S&P 500 / Nasdaq / Dow / gold / silver as AI inputs (default off: they did not help)")
    parser.add_argument("--configs", type=int, default=len(learner.CONFIGS), help=argparse.SUPPRESS)
    parser.add_argument("--db", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--external-db", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--other-markets-db", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--out", type=Path, default=training.CACHE_FILE, help=argparse.SUPPRESS)
    args = parser.parse_args()

    started = time.time()
    repository = MarketDataRepository(args.db) if args.db else MarketDataRepository()
    external = (ExternalDataStore(args.external_db) if args.external_db else ExternalDataStore()).load_all()
    # S&P 500, Nasdaq 100, Dow 30, gold, silver (python -m scripts.update_other_markets)
    external.update((OtherMarketsStore(args.other_markets_db) if args.other_markets_db else OtherMarketsStore()).load_all())
    other_market_features.AI_MODE = args.markets  # also used inside the worker processes (passed below)
    history = load_history(repository)
    tables = indicator_tables(history.candles, ("1h", "4h", "1d", "1w"))
    markets = training.load_markets(history, tables, external)

    print("TRAINING SESSION: the learning engine on every timeframe, 10 setting versions each")
    print("=" * 96)
    print(f"data {history.candles[0].timestamp:%Y-%m-%d} to {history.candles[-1].timestamp:%Y-%m-%d %H:%M} UTC; "
          f"{args.workers} workers; other markets as AI inputs: {args.markets} "
          f"(stored: {', '.join(k[4:] for k in external if k.startswith('mkt.')) or 'none, run update_other_markets'}); versions: " + ", ".join(c.name for c in learner.CONFIGS[:args.configs]))
    cache = training.new_cache()
    cache["markets_mode"] = args.markets  # the app continues with the same inputs
    for tf in args.timeframes:
        t = time.time()
        print(f"\n{tf} chart ({len(markets[tf].candles):,} candles) ...", flush=True)
        cache["timeframes"][tf] = training.train_timeframe(markets, tf, configs=args.configs, memorised=args.memorised,
                                                           workers=args.workers, log=lambda *a: None)
        print(f"  learned in {time.time() - t:.0f} s")
        for h, r in cache["timeframes"][tf]["horizons"].items():
            nested = r["nested"]
            print(f"\n  {tf}, next {horizon_label(tf, h)} ({h} candles): {nested.get('scored', 0):,} forecasts scored")
            print("    each version on its own (whole history, for comparison):")
            for v in sorted(r["configs"], key=lambda v: -v.get("brier_skill", -9)):
                print(f"      {v['name']:<36} skill {pct(v.get('brier_skill'))}   top scenario right {v.get('top_hit_rate', 0):.1%}")
            print("    version used each year (chosen on earlier years only):")
            print("      " + "  ".join(f"{x['year']}:{x['config'][:14]}({pct(x['skill_this_year'])})" for x in r["table"][-6:]))
            print(f"    HONEST result (nested choice): skill {pct(nested.get('brier_skill'))}, log loss skill "
                  f"{pct(nested.get('logloss_skill'))}, top scenario right {nested.get('top_hit_rate', 0):.1%}")
            for k, m in enumerate(r["memorised"], start=2):
                print(f"    memorised pass {k} (has seen these outcomes before, NOT a real result): "
                      f"skill {pct(m.get('brier_skill'))}, top scenario right {m.get('top_hit_rate', 0):.1%}")
            print(f"    version used now: {r['current_config']}")
            print("    pattern experts: " + (", ".join(r.get("experts") or []) or
                                           "off (pip install -r requirements.txt to add trees + analog)"))
            path = training.write_forecast_csv(markets[tf], tf, h, _with_outcomes(markets[tf], r["replay"], h),
                                               args.out.parent)
            print(f"    every forecast: {path}")
    training.save(cache, args.out)
    print(f"\nSaved {args.out} (the app uses it on its next start or data reload).")

    service = EngineService(markets["1d"], history.candles, markets=markets, cache=cache, timeframes=args.timeframes)
    print("\nTODAY'S FORECASTS (from the honest replay):")
    for tf in args.timeframes:
        for h in learner.TF_HORIZONS[tf]:
            s = service.scenarios(h, timeframe=tf)
            if "scenarios" in s:
                print(f"  {tf} next {s['horizon_label']:<9} at {s['candle_time'][:16]}: " + ", ".join(
                    f"{x['kind']} {x['probability']:.0%}" for x in s["scenarios"]) +
                    f"  (targets {s['stop']:,.0f} / {s['target']:,.0f})")
    print(f"\nDone in {time.time() - started:.0f} s. The databases were only read.")


def _with_outcomes(market, replay, horizon):
    from src.predictive_engine.outcomes import outcomes
    replay.outcomes = outcomes(market, horizon, k=1.0)
    return replay


if __name__ == "__main__":
    main()
