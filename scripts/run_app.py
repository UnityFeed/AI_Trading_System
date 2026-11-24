"""
Start the app: a local web page with the overview, the interactive chart
and buttons for the daily routine. Normally started by double-clicking
start_app.bat in the project folder.

Usage:
    python -m scripts.run_app            (start and open the browser)
    python -m scripts.run_app --no-open
"""

import argparse
import socket
import sys
import webbrowser
from pathlib import Path

from src.app.server import AppState, serve
from src.data_collection.external_data import ExternalDataStore
from src.data_collection.other_markets import OtherMarketsStore
from src.data_collection.training_coins import DEFAULT_PATH as COINS_DB
from src.data_collection.market_data_repository import MarketDataRepository
from src.paper_trading.accounts import open_extra_accounts
from src.predictive_engine.forecast_log import ForecastLog
from src.paper_trading.store import PaperTradingStore


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true", help="do not open the browser")
    parser.add_argument("--db", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--paper-db", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--external-db", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--other-markets-db", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--coins-db", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    url = f"http://127.0.0.1:{args.port}/"
    if port_in_use(args.port):
        print(f"The app is already running: opening {url}")
        webbrowser.open(url)
        return

    print("Loading your data and indicators (this takes about 10-30 seconds)...")
    state = AppState(
        MarketDataRepository(args.db) if args.db else MarketDataRepository(),
        PaperTradingStore(args.paper_db) if args.paper_db else PaperTradingStore(),
        ExternalDataStore(args.external_db) if args.external_db else ExternalDataStore(),
        open_extra_accounts(args.paper_db.parent if args.paper_db else None),
        ForecastLog(args.paper_db.parent / "predictions.db") if args.paper_db else ForecastLog(),
        OtherMarketsStore(args.other_markets_db) if args.other_markets_db else OtherMarketsStore(),
        MarketDataRepository(args.coins_db or COINS_DB),
    )
    server = serve(state, args.port)
    print(f"App running at {url}")
    print("Keep this window open while you use the app. Close it (or press Ctrl+C) to stop.")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
