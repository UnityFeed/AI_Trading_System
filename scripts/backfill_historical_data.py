
from datetime import datetime, timezone

from src.data_collection.kraken_trades_provider import (
    KrakenTradesProvider,
)
from src.data_collection.hourly_trade_aggregator import (
    HourlyTradeAggregator,
)
from src.data_collection.historical_backfill_service import (
    HistoricalBackfillService,
)
from src.data_collection.market_data_repository import (
    MarketDataRepository,
)


def main():

    exchange = "kraken"
    symbol = "BTC/USD"
    timeframe = "1h"

    start = datetime(
        2026, 10, 1, 0, 0,
        tzinfo=timezone.utc,
    )

    end = datetime.now(timezone.utc).replace(
        minute=0,
        second=0,
        microsecond=0,
    )

    repository = MarketDataRepository()

    provider = KrakenTradesProvider()
    aggregator = HourlyTradeAggregator()

    service = HistoricalBackfillService(
        provider=provider,
        aggregator=aggregator,
        repository=repository,
    )

    print("=" * 50)
    print(f"{exchange.upper()} HISTORICAL BACKFILL")
    print("=" * 50)
    print(f"Exchange: {exchange}")
    print(f"Symbol: {symbol}")
    print(f"Timeframe: {timeframe}")
    print(f"Start: {start}")
    print(f"End:   {end}")
    print("=" * 50)

    report = service.run(
        start=start,
        end=end,
    )

    print("\nBACKFILL COMPLETE")
    print("=" * 50)

    for key, value in report.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
