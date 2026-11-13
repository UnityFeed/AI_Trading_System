
from datetime import datetime, timedelta, timezone

from src.data_collection.kraken_provider import KrakenProvider
from src.data_collection.market_data_service import MarketDataService


def main():
    provider = KrakenProvider()
    service = MarketDataService(provider)

    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=12)

    print("Connecting to Kraken...")
    print("Requesting BTC/USD hourly candles...")
    print()

    candles = service.get_candles(
        symbol="BTC/USD",
        timeframe="1h",
        start=start,
        end=end,
    )

    print(f"Successfully retrieved {len(candles)} candles.")
    print()

    for candle in candles:
        print(
            f"{candle.timestamp} | "
            f"Open: {candle.open} | "
            f"High: {candle.high} | "
            f"Low: {candle.low} | "
            f"Close: {candle.close} | "
            f"Volume: {candle.volume}"
        )


if __name__ == "__main__":
    main()
