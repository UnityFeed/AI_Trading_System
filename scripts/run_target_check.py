"""
How honest are the AI's price targets? For many past candles (only data known
then), the targets and their chances are computed exactly as the chart shows
them; then we check whether each target was really touched within the
horizon. Prints the calibration (said ~X% -> happened Y%) and the Brier score
compared with a plain "how often is a level this far away touched" rate.

Usage (after a training session, or the app learns first; ~1-5 minutes):
    python -m scripts.run_target_check
    python -m scripts.run_target_check --timeframe 4h --step 12
"""

import argparse
import time
from pathlib import Path

import numpy as np

from src.analysis.technical_indicators import indicator_tables
from src.app.routine import load_history
from src.data_collection.external_data import ExternalDataStore
from src.data_collection.market_data_repository import MarketDataRepository
from src.data_collection.training_coins import DEFAULT_PATH as COINS_DB
from src.predictive_engine import learner, targets, training
from src.predictive_engine.service import EngineService, horizon_label


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeframe", default="1d", choices=("1h", "4h", "1d"))
    parser.add_argument("--step", type=int, default=None, help="check every n-th candle (default: ~1,500 checks)")
    parser.add_argument("--from-year", type=int, default=2017)
    parser.add_argument("--db", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--external-db", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--coins-db", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    started = time.time()
    repository = MarketDataRepository(args.db) if args.db else MarketDataRepository()
    external = (ExternalDataStore(args.external_db) if args.external_db else ExternalDataStore()).load_all()
    history = load_history(repository)
    markets = training.load_markets(history, indicator_tables(history.candles, ("1h", "4h", "1d", "1w")), external)
    coins = MarketDataRepository(args.coins_db or COINS_DB)
    service = EngineService(markets["1d"], history.candles, markets=markets, cache=training.load(), timeframes=(),
                            coin_loader=lambda: training.load_coin_markets(coins))
    tf = args.timeframe
    service.prepare(tf)
    market = markets[tf]
    candles = market.candles
    n = len(candles)
    first = next(i for i, c in enumerate(candles) if c.timestamp.year >= args.from_year)
    step = args.step or max(1, (n - first) // 1500)

    print(f"TARGET CHECK ({tf}): chances of the chart's price targets vs what really happened")
    print("=" * 88)
    for h in learner.TF_HORIZONS[tf]:
        said, hit, base = [], [], []
        exc = targets.excursions(candles, market.consecutive, service.vols[tf], h)
        for i in range(first, n - h, step):
            if exc.known_at[i] == np.inf:
                continue
            for level in service.targets(h, i, tf):
                if level["chance"] is None:
                    continue
                up = level["side"] == "up"
                window = candles[i + 1:i + h + 1]
                touched = max(c.high for c in window) >= level["price"] if up else \
                    min(c.low for c in window) <= level["price"]
                said.append(level["chance"])
                hit.append(touched)
                # plain rate: same distance, ALL past cases (no AI conditioning)
                units = abs(level["distance_pct"]) / 100 / (service.vols[tf][i] * h ** 0.5)
                values = exc.up if up else exc.down
                past = values[(exc.known_at <= i) & ~np.isnan(values)]
                base.append(float((past >= units).mean()) if len(past) else 0.5)
        said, hit, base = np.array(said), np.array(hit, dtype=float), np.array(base)
        if not len(said):
            print(f"\nnext {horizon_label(tf, h)}: no targets to check")
            continue
        brier, brier_base = np.mean((said - hit) ** 2), np.mean((base - hit) ** 2)
        print(f"\nnext {horizon_label(tf, h)}: {len(said):,} targets checked, touched {hit.mean():.0%}")
        print(f"  Brier score {brier:.4f} vs plain distance rate {brier_base:.4f} "
              f"(skill {1 - brier / brier_base:+.1%}; lower Brier = better)")
        print("  calibration:  said      happened   targets")
        for lo in np.arange(0, 1.0, 0.1):
            m = (said >= lo) & (said < lo + 0.1)
            if m.sum() >= 20:
                print(f"               {said[m].mean():5.0%}     {hit[m].mean():5.0%}     {int(m.sum()):>7,}")
    print(f"\nDone in {time.time() - started:.0f} s. The databases were only read.")


if __name__ == "__main__":
    main()
