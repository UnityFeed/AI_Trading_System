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


def main():

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

    repository = MarketDataRepository()

    print("UPDATING RECENT MARKET DATA")
    print("===========================")
    print(f"Symbol: {SYMBOL}")
    print(f"Timeframe: {TIMEFRAME}")
    print(f"Expected latest completed candle: {expected_latest}")
    print()

    for provider in providers:

        exchange = provider.exchange

        latest_before = repository.get_latest_candle_timestamp(
            symbol=SYMBOL,
            market=MARKET,
            timeframe=TIMEFRAME,
            exchange=exchange,
        )

        print(exchange.upper())
        print("-" * len(exchange))

        if latest_before is None:
            print("Skipped: no existing candles found for this exchange.")
            print()
            continue

        latest_before = latest_before.astimezone(timezone.utc)
        start = latest_before + CANDLE_DURATION

        if start >= end:
            print("No newer completed hour to request.")
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

                print(f"Requested from: {start}")
                print(f"Candles returned: {len(candles):,}")
                print(f"Database rows processed: {rows_processed:,}")

            except Exception as exc:
                print(f"Update failed: {exc}")
                print()
                continue

        lag_hours = int(
            (expected_latest - latest_after).total_seconds()
            // CANDLE_DURATION.total_seconds()
        )

        print(f"Latest stored candle: {latest_after}")

        if lag_hours == 0:
            print("Freshness: current through the latest completed hour.")
        elif lag_hours > 0:
            print(f"Freshness: {lag_hours} completed hour(s) behind.")
        else:
            print("Freshness: stored data is ahead of the expected hour.")

        print()

    print("Update complete. No incomplete current-hour candle was requested.")


if __name__ == "__main__":
    main()