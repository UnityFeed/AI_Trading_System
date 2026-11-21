"""
The daily routine, in one command:

1. update the hourly candles of Kraken, Bitstamp and Coinbase
2. let the paper trader process every new completed daily candle
3. rebuild the dashboard (reports/dashboard.html)

The first run creates a paper account with $10,000 of virtual money. By
default it replays the strategy from 1 January of this year so the page
has something to show right away; choose another start with --start.

Usage:
    python -m scripts.daily_run
    python -m scripts.daily_run --open                  (open the page afterwards)
    python -m scripts.daily_run --start 2026-11-21      (first run only: start date)
    python -m scripts.daily_run --skip-update           (no internet / data already fresh)
"""

import argparse
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from scripts import update_all_exchanges
from scripts.build_dashboard import HISTORY_START, build
from src.analysis.primary_history import get_continuous_history
from src.data_collection.market_data_repository import MarketDataRepository
from src.paper_trading.store import PaperTradingStore
from src.paper_trading.trader import PaperTrader


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", help="first day the paper account acts on (YYYY-MM-DD), first run only")
    parser.add_argument("--skip-update", action="store_true", help="do not download new candles")
    parser.add_argument("--open", action="store_true", help="open the dashboard afterwards")
    parser.add_argument("--db", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--paper-db", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    if not args.skip_update:
        print("STEP 1/3  Updating market data")
        update_all_exchanges.main()
    else:
        print("STEP 1/3  Skipped data update")

    print("STEP 2/3  Paper trading")
    repository = MarketDataRepository(args.db) if args.db else MarketDataRepository()
    store = PaperTradingStore(args.paper_db) if args.paper_db else PaperTradingStore()
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    history = get_continuous_history(repository=repository, start=HISTORY_START, end=end)

    trader = PaperTrader(store)
    if store.get_account() is None:
        start = (
            datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
            if args.start else datetime(end.year, 1, 1, tzinfo=timezone.utc)
        )
        print(f"  New paper account: $10,000, acting from {start:%Y-%m-%d}")
        trader.ensure_account(start)
    elif args.start:
        print("  --start ignored: the paper account already exists.")

    report = trader.step(history)
    for line in report.warnings:
        print(f"  WARNING: {line}")
    print(f"  {len(report.decisions)} new decision(s), {len(report.fills)} new fill(s)")
    for line in report.decisions[-5:]:
        print(f"    {line}")
    for line in report.fills:
        print(f"    FILL {line}")

    print("STEP 3/3  Building the dashboard")
    path = build(repository, store, history)
    print(f"  Dashboard: {path}")
    if args.open:
        webbrowser.open(path.as_uri())


if __name__ == "__main__":
    main()
