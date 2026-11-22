"""
Quick system check: is the market database there, how fresh is it, and is
there a paper account? Read-only; it never creates or changes a database.

    python main.py

To use the system, double-click start_app.bat (or: python -m scripts.run_app).
"""

import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from src.data_collection.market_data_repository import MarketDataRepository
from src.paper_trading.accounts import EXTRA_ACCOUNTS
from src.paper_trading.store import DEFAULT_PATH as PAPER_DB


def read_only(path):
    """Open an existing SQLite file read-only (fails instead of creating it)."""
    return closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True))


def main() -> None:
    print("AI TRADING SYSTEM - status")
    print("Trading mode: paper trading only (live trading is not enabled)")
    print()

    market_db = MarketDataRepository.default_path()
    if not market_db.is_file():
        print(f"Market database: NOT FOUND at {market_db}")
    else:
        try:
            with read_only(market_db) as connection:
                rows = connection.execute("""
                    SELECT exchange, COUNT(*), MAX(timestamp) FROM market_candles
                    WHERE symbol = 'BTC/USD' AND timeframe = '1h'
                    GROUP BY exchange ORDER BY exchange
                """).fetchall()
        except sqlite3.Error as exc:
            print(f"Market database: cannot be read ({exc})")
        else:
            now = datetime.now(timezone.utc)
            print(f"Market database: {market_db}")
            for exchange, count, latest in rows:
                hours_old = (now - datetime.fromisoformat(latest)).total_seconds() / 3600
                print(f"  {exchange:<9} {count:>8,} hourly candles, latest {latest} ({hours_old:.0f} h ago)")

    print()
    accounts = [("Paper account (main)", PAPER_DB)] + [
        (f"Paper account '{a.id}'", PAPER_DB.parent / a.filename) for a in EXTRA_ACCOUNTS
    ]
    for label, path in accounts:
        account = None
        if path.is_file():
            with read_only(path) as connection:
                account = connection.execute(
                    "SELECT strategy, starting_cash, cash, btc FROM account WHERE id = 1"
                ).fetchone()
        if account is None:
            print(f"{label}: none yet (created by the first daily run)")
        else:
            strategy, start, cash, btc = account
            print(f"{label}: {strategy}")
            print(f"  started with ${start:,.2f}; now ${cash:,.2f} cash and {btc:.6f} BTC")

    print()
    print("Start the app: double-click start_app.bat (or: python -m scripts.run_app)")


if __name__ == "__main__":
    main()
