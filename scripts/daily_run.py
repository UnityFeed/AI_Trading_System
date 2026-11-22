"""
The daily routine from the terminal: update the data, run the paper
trader, rebuild the dashboard page. (The app's button does the same:
see start_app.bat.)

The first run creates a paper account with $10,000 of virtual money and
replays the strategy from 1 January of this year; choose another start
with --start.

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

from scripts.build_dashboard import build
from src.app.routine import daily_routine
from src.data_collection.external_data import ExternalDataStore
from src.data_collection.market_data_repository import MarketDataRepository
from src.paper_trading.store import PaperTradingStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", help="first day the paper account acts on (YYYY-MM-DD), first run only")
    parser.add_argument("--skip-update", action="store_true", help="do not download new candles")
    parser.add_argument("--open", action="store_true", help="open the dashboard afterwards")
    parser.add_argument("--db", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--paper-db", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    repository = MarketDataRepository(args.db) if args.db else MarketDataRepository()
    store = PaperTradingStore(args.paper_db) if args.paper_db else PaperTradingStore()
    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc) if args.start else None

    history = daily_routine(repository, store, update=not args.skip_update, start=start,
                            external_store=ExternalDataStore())

    path = build(repository, store, history)
    print(f"Dashboard: {path}")
    if args.open:
        webbrowser.open(path.as_uri())


if __name__ == "__main__":
    main()
