from datetime import datetime, timezone

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

    # Use only completed hourly candles.
    end = datetime.now(timezone.utc).replace(
        minute=0,
        second=0,
        microsecond=0,
    )

    repository = MarketDataRepository()

    print("BTC/USD HOURLY RETURN SUMMARY")
    print("=============================")
    print(f"Period requested: {start} to {end}")
    print("Returns are calculated separately for each exchange.")
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

        clean_candles = get_clean_candles(
            repository=repository,
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            start=start,
            end=end,
            exchange=exchange,
        )

        hourly_returns = calculate_hourly_returns(clean_candles)

        print(f"{exchange.upper()}")
        print("-" * len(exchange))

        print(f"Stored candles: {len(stored_candles):,}")
        print(f"Available candles: {len(clean_candles):,}")
        print(
            "Excluded (quality list + zero volume): "
            f"{len(stored_candles) - len(clean_candles):,}"
        )
        print(f"Consecutive-hour returns: {len(hourly_returns):,}")

        if not hourly_returns:
            print("No consecutive hourly returns available.")
            print()
            continue

        average_return = sum(
            item.return_pct for item in hourly_returns
        ) / len(hourly_returns)

        positive_count = sum(
            item.return_pct > 0 for item in hourly_returns
        )
        negative_count = sum(
            item.return_pct < 0 for item in hourly_returns
        )
        unchanged_count = sum(
            item.return_pct == 0 for item in hourly_returns
        )

        best_return = max(
            hourly_returns,
            key=lambda item: item.return_pct,
        )
        worst_return = min(
            hourly_returns,
            key=lambda item: item.return_pct,
        )

        print(f"Average hourly return: {average_return:.6f}%")
        print(f"Positive hours: {positive_count:,}")
        print(f"Negative hours: {negative_count:,}")
        print(f"Unchanged hours: {unchanged_count:,}")
        print(
            f"Largest positive return: {best_return.return_pct:.4f}% "
            f"at {best_return.timestamp}"
        )
        print(
            f"Largest negative return: {worst_return.return_pct:.4f}% "
            f"at {worst_return.timestamp}"
        )
        print()

    print("Report complete. The database was only read.")


if __name__ == "__main__":
    main()