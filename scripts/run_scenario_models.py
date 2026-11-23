"""
Scenario models (predictive engine, phase 3): how well do the base, structure
and analog models predict bull / bear / range over the next 30 days, on years
they did not learn from (walk-forward from 2017)?

Shows for each model: multi-class Brier score and log loss, the skill
compared with the plain base rate, and a calibration table (when the model
said ~40%, how often did it happen?). Ends with today's scenarios from the
model the chart uses (src/predictive_engine/engine.py MODEL).

The database is only read.

Usage:
    python -m scripts.run_scenario_models
"""

import argparse
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from src.app.routine import load_history
from src.backtesting.market import build_market
from src.data_collection.external_data import ExternalDataStore
from src.data_collection.market_data_repository import MarketDataRepository
from src.predictive_engine import engine
from src.predictive_engine.scenarios import KINDS, score, walk_forward


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--db", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--external-db", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    started = time.time()
    repository = MarketDataRepository(args.db) if args.db else MarketDataRepository()
    external = (ExternalDataStore(args.external_db) if args.external_db else ExternalDataStore()).load_all()
    history = load_history(repository)
    market = build_market(history, "1d", external=external)
    # the same inputs as the app (no Coinbase premium), so both show the same numbers
    ctx = engine.engine_context(market)

    print(f"SCENARIO MODELS: bull / bear / range over {engine.HORIZON} days, walk-forward from 2017")
    print("=" * 88)
    scores = {}
    with ProcessPoolExecutor(args.workers or os.cpu_count() or 1) as pool:
        for model in ("base", "structure", "analog"):
            t = time.time()
            forecasts = walk_forward(ctx, model, 2017, pool)
            scores[model] = score(ctx, forecasts)
            s = scores[model]
            print(f"{model:<10} {s.n:,} days  Brier {s.brier:.4f}  log loss {s.log_loss:.4f}  ({time.time() - t:.0f} s)")
    base = scores["base"]
    print()
    print("Skill compared with the base rate (1 = perfect, 0 = no better, below 0 = worse):")
    for model in ("structure", "analog"):
        s = scores[model]
        print(f"  {model:<10} Brier skill {1 - s.brier / base.brier:+.3f}   log-loss skill {1 - s.log_loss / base.log_loss:+.3f}")
    print()
    for model in ("structure", "analog"):
        print(f"Calibration, {model} (predicted -> happened, days):")
        for kind in KINDS:
            print(f"  {kind:<6} " + ", ".join(f"{a:.2f}->{b:.2f} ({n})" for a, b, n in scores[model].calibration[kind]))
    print()
    today = engine.todays_scenarios(market, ctx).as_dict()
    print(f"TODAY ({today['candle_time'][:10]} close {today['close']:,.0f}; daily trend {today['daily_trend']}, "
          f"weekly trend {today['weekly_trend']}), model {today['model_version']}, {today['cases']} similar past days:")
    for s in today["scenarios"]:
        print(f"  {s['kind']:<6} {s['probability']:5.1%}  {s['meaning']}; typical {s['typical_days']} days; "
              f"proven wrong by {s['proven_wrong_by']}")
    print(f"\nDone in {time.time() - started:.0f} s. The database was only read.")


if __name__ == "__main__":
    main()
