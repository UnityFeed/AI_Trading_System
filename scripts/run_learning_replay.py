"""
The learning engine's report card (predictive engine): it is replayed from
the first day of data to today, one day at a time, seeing only what was known
each day, and learning from every outcome as it arrives.

Shows per horizon (7, 14, 30 days): its score against the plain base rate
(Brier skill), how often its most likely scenario was right, each expert's
own score and the blend's current weights, and the learning curve per year.
Plus the track record of every chart pattern type on the daily chart, and
today's forecast for each horizon.

The database is only read.

Usage:
    python -m scripts.run_learning_replay
"""

import argparse
import time
from pathlib import Path

from src.app.routine import load_history
from src.backtesting.market import build_market
from src.data_collection.external_data import ExternalDataStore
from src.data_collection.market_data_repository import MarketDataRepository
from src.predictive_engine import learner
from src.predictive_engine.patterns import detect_patterns, track_record
from src.predictive_engine.service import EngineService


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-year", type=int, default=2017, help="score forecasts from this year on")
    parser.add_argument("--db", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--external-db", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    started = time.time()
    repository = MarketDataRepository(args.db) if args.db else MarketDataRepository()
    external = (ExternalDataStore(args.external_db) if args.external_db else ExternalDataStore()).load_all()
    history = load_history(repository)
    market = build_market(history, "1d", external=external)
    service = EngineService(market, history.candles)
    candles = market.candles

    print("LEARNING ENGINE REPLAY: day by day from the first day of data, learning as outcomes arrive")
    print("=" * 92)
    print(f"{candles[0].timestamp:%Y-%m-%d} to {candles[-1].timestamp:%Y-%m-%d}; experts: {', '.join(learner.EXPERTS)}; "
          f"scored from {args.from_year}")
    for h in learner.HORIZONS:
        r = service.replays[h]
        n = b = bb = hits = 0
        per_expert = {e: 0.0 for e in learner.EXPERTS}
        for i, (p, o) in enumerate(zip(r.forecasts, r.outcomes)):
            if p is None or o is None or candles[i].timestamp.year < args.from_year:
                continue
            n += 1
            b += learner.brier(p, o.kind)
            bb += learner.brier(r.experts[i]["base"], o.kind)
            hits += max(p, key=p.get) == o.kind
            for e in learner.EXPERTS:
                per_expert[e] += learner.brier(r.experts[i][e], o.kind)
        print(f"\n{h}-day horizon: {n:,} forecasts scored")
        print(f"  engine skill vs base rate {1 - b / bb:+.2%}   most likely scenario right {hits / n:.1%}")
        print("  experts on their own: " + "  ".join(f"{e} {1 - per_expert[e] / bb:+.2%}" for e in learner.EXPERTS))
        print("  blend weights now: " + "  ".join(f"{e} {w:.0%}" for e, w in r.weights[-1].items()))
        print("  learning curve (skill per year): " + "  ".join(f"{y}:{1 - s / base:+.1%}" for y, _, s, base in r.learning_curve))
        today = service.scenarios(h)
        print(f"  today ({today['candle_time'][:10]}): " + ", ".join(
            f"{s['kind']} {s['probability']:.0%}" for s in today["scenarios"]) +
            f"  (targets {today['stop']:,.0f} / {today['target']:,.0f})")

    print("\nCHART PATTERNS on the daily chart (only from swings confirmed at the time):")
    print(f"  {'pattern':<28}{'found':>6}{'broke out':>10}{'hit target':>11}{'failed':>8}{'expired':>8}{'hit rate':>9}")
    for kind, r in sorted(track_record(detect_patterns(candles, "1d")).items()):
        rate = "-" if r["hit_rate"] is None else f"{r['hit_rate']:.0%}"
        print(f"  {kind:<28}{r['detected']:>6}{r['confirmed']:>10}{r['hit']:>11}{r['failed']:>8}{r['expired']:>8}{rate:>9}")
    print(f"\nDone in {time.time() - started:.0f} s. The database was only read.")


if __name__ == "__main__":
    main()
