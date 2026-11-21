from datetime import datetime, timezone

from src.data_collection.bitstamp_provider import BitstampProvider
from src.data_collection.market_data_repository import MarketDataRepository
from src.data_collection.market_data_service import MarketDataService


def main():

    exchange = "bitstamp"
    symbol = "BTC/USD"
    timeframe = "1h"

    # Match the beginning of the Kraken hourly archive.
    start = datetime(2013, 10, 6, 0, 0, tzinfo=timezone.utc)

    # Stop at the start of the current hour.
    end = datetime.now(timezone.utc).replace(
        minute=0,
        second=0,
        microsecond=0,
    )

    repository = MarketDataRepository()
    provider = BitstampProvider()
    service = MarketDataService(provider)

    print("=" * 50)
    print(f"{exchange.upper()} HISTORICAL DATA IMPORT")
    print("=" * 50)
    print(f"Exchange: {exchange}")
    print(f"Symbol: {symbol}")
    print(f"Timeframe: {timeframe}")
    print(f"Start: {start}")
    print(f"End:   {end}")
    print("=" * 50)
    print("Fetching candles. This may take a little while...")

    candles = service.get_candles(
        symbol=symbol,
        timeframe=timeframe,
        start=start,
        end=end,
    )

    rows_processed = repository.save_candles(
        candles=candles,
        timeframe=timeframe,
    )

    print("\nIMPORT COMPLETE")
    print("=" * 50)
    print(f"Candles returned: {len(candles):,}")
    print(f"Database rows processed: {rows_processed:,}")
    print(f"Database: {repository.db_path}")


if __name__ == "__main__":
    main()