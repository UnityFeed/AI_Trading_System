"""
The daily routine, shared by the terminal command (scripts/daily_run.py)
and the app's button:

1. update the hourly candles of Kraken, Bitstamp, Coinbase and Bybit
   (the market database is backed up once a day first)
2. update the free external daily data (Coin Metrics: MVRV, market cap,
   hash rate) and the other markets (S&P 500, Nasdaq 100, Dow 30, gold,
   silver), when their stores are given; a failure here is reported but
   does not stop the routine
3. let the paper trader process every new completed candle
   (and run every extra paper account side by side, src/paper_trading/accounts.py)
"""

from datetime import datetime, timezone

from src.analysis.primary_history import ContinuousHistory, get_trading_history
from src.data_collection.exchange_updater import update_all_exchanges
from src.data_collection.external_data import ExternalDataStore, update_external_data
from src.data_collection.market_data_repository import MarketDataRepository
from src.data_collection.other_markets import OtherMarketsStore, update_other_markets
from src.paper_trading.store import PaperTradingStore
from src.paper_trading.trader import STARTING_CASH, PaperTrader


HISTORY_START = datetime(2013, 1, 1, tzinfo=timezone.utc)


def load_history(repository: MarketDataRepository) -> ContinuousHistory:
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return get_trading_history(repository=repository, start=HISTORY_START, end=end)  # Bitstamp, gaps filled


def daily_routine(
    repository: MarketDataRepository,
    store: PaperTradingStore,
    update: bool = True,
    start: datetime | None = None,
    log=print,
    external_store: ExternalDataStore | None = None,
    extra_accounts=(),
    other_markets_store: OtherMarketsStore | None = None,
) -> ContinuousHistory:
    """`extra_accounts`: (ExtraAccount, PaperTradingStore) pairs run after the main account."""
    """Run the routine and return the refreshed history."""

    if update:
        log("STEP 1/3  Updating market data")
        update_all_exchanges(repository, log=lambda *parts: log("  " + " ".join(map(str, parts))))
    else:
        log("STEP 1/3  Skipped data update")

    if update and external_store is not None:
        log("STEP 2/3  Updating external data (Coin Metrics)")
        try:
            update_external_data(external_store, log=lambda *parts: log(" ".join(map(str, parts))))
        except Exception as error:  # needs internet; never blocks the paper trader
            log(f"  WARNING: external data not updated: {error}")
    else:
        log("STEP 2/3  Skipped external data update")

    if update and other_markets_store is not None:
        log("          Updating other markets (S&P 500, Nasdaq 100, Dow 30, gold, silver; Yahoo Finance)")
        try:
            update_other_markets(other_markets_store, log=lambda *parts: log("  " + " ".join(map(str, parts))))
        except Exception as error:  # needs internet; never blocks the paper trader
            log(f"  WARNING: other markets not updated: {error}")

    log("STEP 3/3  Paper trading")
    history = load_history(repository)
    external = external_store.load_all() if external_store is not None else {}
    trader = PaperTrader(store, external=external)

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

    for config, extra_store in extra_accounts:
        definition = config.definition
        log(f"  Paper account '{config.id}': {definition.name}")
        try:
            extra = PaperTrader(extra_store, definition.exposure or definition.spec, definition.timeframe,
                                external=external)
            if extra_store.get_account() is None:
                log(f"    New paper account: ${config.starting_cash:,.0f}, acting from {config.start:%Y-%m-%d}")
                extra.ensure_account(config.start, cash=config.starting_cash)
            step = extra.step(history)
        except Exception as error:  # one account failing must not stop the others
            log(f"    ERROR: {error}")
            continue
        for line in step.warnings:
            log(f"    WARNING: {line}")
        log(f"    {len(step.decisions)} new decision(s), {len(step.fills)} new fill(s)")
        for line in step.decisions[-3:]:
            log(f"      {line}")
        for line in step.fills:
            log(f"      FILL {line}")
    return history
