from datetime import datetime, timezone

from src.analysis.indicators import calculate_hourly_sma
from src.analysis.market_data_quality import get_clean_candles
from src.analysis.returns import calculate_hourly_returns
from src.data_collection.market_data_repository import MarketDataRepository


def main():

    symbol = "BTC/USD"
    market = "crypto"
    timeframe = "1h"
    exchanges = ("bitstamp", "coinbase", "kraken")

    start = datetime(
        2013, 10, 6, 0, 0,
        tzinfo=timezone.utc,
    )

    end = datetime.now(timezone.utc).replace(
        minute=0,
        second=0,
        microsecond=0,
    )

    repository = MarketDataRepository()

    print("BTC/USD HOURLY ANALYSIS SUMMARY")
    print("===============================")
    print(f"Period requested: {start} to {end}")
    print()

    for exchange in exchanges:

        stored_candles = repository.get_candles(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            start=start,
            end=end,
            exchange=exchange,
        )

        candles = get_clean_candles(
            repository=repository,
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            start=start,
            end=end,
            exchange=exchange,
        )

        hourly_returns = calculate_hourly_returns(candles)
        sma_24 = calculate_hourly_sma(candles, period_hours=24)
        sma_168 = calculate_hourly_sma(candles, period_hours=168)

        print(exchange.upper())
        print("-" * len(exchange))
        print(f"Stored candles: {len(stored_candles):,}")
        print(f"Available candles: {len(candles):,}")
        print(
            "Excluded (quality list + zero volume): "
            f"{len(stored_candles) - len(candles):,}"
        )
        print(f"Consecutive-hour returns: {len(hourly_returns):,}")

        if candles:
            latest_candle = candles[-1]
            print(
                f"Latest close: {latest_candle.close:.8f} "
                f"at {latest_candle.timestamp}"
            )

        if hourly_returns:
            latest_return = hourly_returns[-1]
            print(
                f"Latest hourly return: {latest_return.return_pct:.6f}% "
                f"at {latest_return.timestamp}"
            )

        if sma_24:
            latest_24 = sma_24[-1]
            print(
                f"Latest 24-hour SMA: {latest_24.value:.8f} "
                f"at {latest_24.timestamp}"
            )
        else:
            print("24-hour SMA: not enough consecutive hourly candles.")

        if sma_168:
            latest_168 = sma_168[-1]
            print(
                f"Latest 168-hour SMA: {latest_168.value:.8f} "
                f"at {latest_168.timestamp}"
            )
        else:
            print("168-hour SMA: not enough consecutive hourly candles.")

        if hourly_returns:
            average_return = sum(
                item.return_pct for item in hourly_returns
            ) / len(hourly_returns)

            print(f"Average hourly return: {average_return:.6f}%")

        print()

    print("Report complete. The database was only read.")


if __name__ == "__main__":
    main()