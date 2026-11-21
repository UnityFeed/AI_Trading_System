"""
Forward update of the hourly candles of Kraken, Bitstamp and Coinbase.

Used by scripts/update_all_exchanges.py, the daily routine and the app.
"""

from datetime import datetime, timedelta, timezone

from src.data_collection.bitstamp_provider import BitstampProvider
from src.data_collection.coinbase_provider import CoinbaseProvider
from src.data_collection.kraken_provider import KrakenProvider
from src.data_collection.market_data_repository import MarketDataRepository
from src.data_collection.market_data_service import MarketDataService


SYMBOL = "BTC/USD"
MARKET = "crypto"
TIMEFRAME = "1h"
CANDLE_DURATION = timedelta(hours=1)


def update_all_exchanges(repository: MarketDataRepository | None = None, log=print) -> None:
    """Fetch new completed hourly candles for every exchange (forward only)."""

    providers = (
        BitstampProvider(),
        CoinbaseProvider(),
        KrakenProvider(),
    )

    # The current hour is incomplete, so request candles only up to its start.
    end = datetime.now(timezone.utc).replace(
        minute=0,
        second=0,
        microsecond=0,
    )
    expected_latest = end - CANDLE_DURATION

    repository = repository or MarketDataRepository()

    log("UPDATING RECENT MARKET DATA")
    log("===========================")
    log(f"Symbol: {SYMBOL}")
    log(f"Timeframe: {TIMEFRAME}")
    log(f"Expected latest completed candle: {expected_latest}")
    log()

    for provider in providers:

        exchange = provider.exchange

        latest_before = repository.get_latest_candle_timestamp(
            symbol=SYMBOL,
            market=MARKET,
            timeframe=TIMEFRAME,
            exchange=exchange,
        )

        log(exchange.upper())
        log("-" * len(exchange))

        if latest_before is None:
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
                    symbol=SYMBOL,
                    timeframe=TIMEFRAME,
                    start=start,
                    end=end,
                )

                rows_processed = repository.save_candles(
                    candles=candles,
                    timeframe=TIMEFRAME,
                )

                latest_after = repository.get_latest_candle_timestamp(
                    symbol=SYMBOL,
                    market=MARKET,
                    timeframe=TIMEFRAME,
                    exchange=exchange,
                ).astimezone(timezone.utc)

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
