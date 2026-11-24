"""
Forward update of the hourly candles of Kraken, Bitstamp, Coinbase and Bybit.

Used by scripts/update_all_exchanges.py, the daily routine and the app.
Before writing, the market database is backed up once per day
(database/backups/, newest 7 kept). Bybit (BTC/USDT, the owner's exchange)
is downloaded in full on its first update (from 2021, ~50 requests, about a
minute); after that it is updated forward like the others.
"""

from datetime import datetime, timedelta, timezone

from src.data_collection.backup import backup_database
from src.data_collection.bitstamp_provider import BitstampProvider
from src.data_collection.bybit_provider import BybitProvider
from src.data_collection.coinbase_provider import CoinbaseProvider
from src.data_collection.kraken_provider import KrakenProvider
from src.data_collection.market_data_repository import MarketDataRepository
from src.data_collection.market_data_service import MarketDataService


SYMBOL = "BTC/USD"
SYMBOLS = {"bybit": "BTC/USDT"}  # exchanges whose BTC market has another symbol
FULL_FIRST_DOWNLOAD = {"bybit": BybitProvider.FIRST_AVAILABLE}  # no stored candles yet: download from here
MARKET = "crypto"
TIMEFRAME = "1h"
CANDLE_DURATION = timedelta(hours=1)


def update_all_exchanges(repository: MarketDataRepository | None = None, log=print, providers=None,
                         backup: bool = True) -> None:
    """Fetch new completed hourly candles for every exchange (forward only)."""

    providers = providers or (
        BitstampProvider(),
        CoinbaseProvider(),
        KrakenProvider(),
        BybitProvider(),
    )

    # The current hour is incomplete, so request candles only up to its start.
    end = datetime.now(timezone.utc).replace(
        minute=0,
        second=0,
        microsecond=0,
    )
    expected_latest = end - CANDLE_DURATION

    repository = repository or MarketDataRepository()
    if backup:
        try:
            copy = backup_database(repository.db_path)
            if copy:
                log(f"Backup: {copy}")
        except Exception as exc:  # a failed backup must not stop the update, but is reported
            log(f"Backup FAILED: {exc}")

    log("UPDATING RECENT MARKET DATA")
    log("===========================")
    log(f"Symbol: {SYMBOL}")
    log(f"Timeframe: {TIMEFRAME}")
    log(f"Expected latest completed candle: {expected_latest}")
    log()

    for provider in providers:

        exchange = provider.exchange
        symbol = SYMBOLS.get(exchange, SYMBOL)

        latest_before = repository.get_latest_candle_timestamp(
            symbol=symbol,
            market=MARKET,
            timeframe=TIMEFRAME,
            exchange=exchange,
        )

        log(exchange.upper())
        log("-" * len(exchange))

        if latest_before is None and exchange in FULL_FIRST_DOWNLOAD:
            log(f"First download: full history from {FULL_FIRST_DOWNLOAD[exchange]:%Y-%m-%d} (about a minute).")
            latest_before = FULL_FIRST_DOWNLOAD[exchange] - CANDLE_DURATION
        elif latest_before is None:
            log("Skipped: no existing candles found for this exchange.")
            log()
            continue

        latest_before = latest_before.astimezone(timezone.utc)
        start = latest_before + CANDLE_DURATION

        if start >= end:
            log("No newer completed hour to request.")
            latest_after = latest_before
        else:
            try:
                service = MarketDataService(provider)

                candles = service.get_candles(
                    symbol=symbol,
                    timeframe=TIMEFRAME,
                    start=start,
                    end=end,
                )

                rows_processed = repository.save_candles(
                    candles=candles,
                    timeframe=TIMEFRAME,
                )

                latest_after = repository.get_latest_candle_timestamp(
                    symbol=symbol,
                    market=MARKET,
                    timeframe=TIMEFRAME,
                    exchange=exchange,
                )
                if latest_after is None:
                    log("No candles returned.")
                    log()
                    continue
                latest_after = latest_after.astimezone(timezone.utc)

                log(f"Requested from: {start}")
                log(f"Candles returned: {len(candles):,}")
                log(f"Database rows processed: {rows_processed:,}")

            except Exception as exc:
                log(f"Update failed: {exc}")
                log()
                continue

        lag_hours = int(
            (expected_latest - latest_after).total_seconds()
            // CANDLE_DURATION.total_seconds()
        )

        log(f"Latest stored candle: {latest_after}")

        if lag_hours == 0:
            log("Freshness: current through the latest completed hour.")
        elif lag_hours > 0:
            log(f"Freshness: {lag_hours} completed hour(s) behind.")
        else:
            log("Freshness: stored data is ahead of the expected hour.")

        log()

    log("Update complete. No incomplete current-hour candle was requested.")
