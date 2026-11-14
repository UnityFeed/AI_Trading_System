
from datetime import datetime, timedelta, timezone

from src.data_collection.kraken_provider import KrakenProvider
from src.data_collection.market_data_service import MarketDataService
from src.data_collection.market_data_repository import MarketDataRepository


def main():

    end = datetime.now(timezone.utc).replace(
        minute=0,
        second=0,
        microsecond=0,
    )

    start = end - timedelta(hours=719)

    provider = KrakenProvider()
    service = MarketDataService(provider)
    repository = MarketDataRepository()

    print("Fetching recent BTC/USD hourly candles...")
    print("Start:", start)
    print("End:", end)

    candles = service.get_candles(
        symbol="BTC/USD",
        timeframe="1h",
        start=start,
        end=end,
    )

    saved = repository.save_candles(
        candles=candles,
        timeframe="1h",
    )

    print("\nPULL COMPLETE")
    print("Candles received:", len(candles))
    print("Rows saved:", saved)

    if candles:
        print("First candle:", candles[0].timestamp)
        print("Last candle:", candles[-1].timestamp)


if __name__ == "__main__":
    main()
