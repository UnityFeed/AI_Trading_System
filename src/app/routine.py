"""
The daily routine, shared by the terminal command (scripts/daily_run.py)
and the app's button:

1. update the hourly candles of Kraken, Bitstamp and Coinbase
2. let the paper trader process every new completed candle
"""

from datetime import datetime, timezone

from src.analysis.primary_history import ContinuousHistory, get_continuous_history
from src.data_collection.exchange_updater import update_all_exchanges
from src.data_collection.market_data_repository import MarketDataRepository
from src.paper_trading.store import PaperTradingStore
from src.paper_trading.trader import STARTING_CASH, PaperTrader


HISTORY_START = datetime(2013, 1, 1, tzinfo=timezone.utc)


def load_history(repository: MarketDataRepository) -> ContinuousHistory:
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return get_continuous_history(repository=repository, start=HISTORY_START, end=end)


def daily_routine(
    repository: MarketDataRepository,
    store: PaperTradingStore,
    update: bool = True,
    start: datetime | None = None,
    log=print,
) -> ContinuousHistory:
    """Run the routine and return the refreshed history."""

    if update:
        log("STEP 1/2  Updating market data")
        update_all_exchanges(repository, log=lambda *parts: log("  " + " ".join(map(str, parts))))
    else:
        log("STEP 1/2  Skipped data update")

    log("STEP 2/2  Paper trading")
    history = load_history(repository)
    trader = PaperTrader(store)

    if store.get_account() is None:
        now = datetime.now(timezone.utc)
        start = start or datetime(now.year, 1, 1, tzinfo=timezone.utc)
        log(f"  New paper account: ${STARTING_CASH:,.0f}, acting from {start:%Y-%m-%d}")
        trader.ensure_account(start)
    elif start is not None:
        log("  Start date ignored: the paper account already exists.")

    report = trader.step(history)
    for line in report.warnings:
        log(f"  WARNING: {line}")
    log(f"  {len(report.decisions)} new decision(s), {len(report.fills)} new fill(s)")
    for line in report.decisions[-5:]:
        log(f"    {line}")
    for line in report.fills:
        log(f"    FILL {line}")
    return history
