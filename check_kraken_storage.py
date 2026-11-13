
from datetime import datetime, timedelta, timezone

from src.data_collection.kraken_provider import KrakenProvider
from src.data_collection.market_data_service import MarketDataService
from src.data_collection.market_data_repository import MarketDataRepository


def main():

    provider = KrakenProvider()
    service = MarketDataService(provider)
    repository = MarketDataRepository()

    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=12)

    print("Retrieving BTC/USD candles from Kraken...")

    candles = service.get_candles(
        symbol="BTC/USD",
        timeframe="1h",
        start=start,
        end=end,
    )

    print(f"Retrieved {len(candles)} candles.")

    print("\nSaving candles to SQLite...")

    saved = repository.save_candles(
        candles=candles,
        timeframe="1h",
    )

    print(f"Saved {saved} candles.")

    print("\nReading candles back from SQLite...")

    stored_candles = repository.get_candles(
        symbol="BTC/USD",
        market="crypto",
        timeframe="1h",
        start=start,
        end=end,
    )

    print(f"Retrieved {len(stored_candles)} stored candles.")

    print("\nStored candle data:")

    for candle in stored_candles:
        print(
            f"{candle.timestamp} | "
            f"Close: {candle.close} | "
            f"Volume: {candle.volume}"
        )

    if len(stored_candles) != len(candles):
        raise RuntimeError("Stored candle count does not match.")

    print("\nSUCCESS: Kraken data was saved and retrieved correctly.")


if __name__ == "__main__":
    main()
