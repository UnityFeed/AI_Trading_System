
from datetime import datetime, timedelta, timezone

from src.data_collection.kraken_trades_provider import (
    KrakenTradesProvider,
)
from src.data_collection.hourly_trade_aggregator import (
    HourlyTradeAggregator,
)
from src.data_collection.market_data_repository import (
    MarketDataRepository,
)


class HistoricalBackfillService:
    """
    Reconstructs historical hourly Kraken candles from individual trades.

    Data is fetched and saved in daily batches.
    """

    TIMEFRAME = "1h"

    def __init__(
        self,
        provider: KrakenTradesProvider,
        aggregator: HourlyTradeAggregator,
        repository: MarketDataRepository,
    ):
        self.provider = provider
        self.aggregator = aggregator
        self.repository = repository

        provider_exchange = getattr(
            provider, "exchange", None
        )

        aggregator_exchange = getattr(
            aggregator, "EXCHANGE", None
        )

        if not provider_exchange or not aggregator_exchange:
            raise ValueError(
                "Provider and aggregator must define their exchange."
            )

        if provider_exchange.lower() != aggregator_exchange.lower():
            raise ValueError(
                "Provider and aggregator exchanges do not match."
            )

        self.exchange = provider_exchange.lower()

    def run(
        self,
        start: datetime,
        end: datetime,
    ) -> dict:

        if (
            start.tzinfo is None
            or start.utcoffset() is None
            or end.tzinfo is None
            or end.utcoffset() is None
        ):
            raise ValueError(
                "Start and end must be timezone-aware."
            )

        start = start.astimezone(timezone.utc)
        end = end.astimezone(timezone.utc)

        if start >= end:
            raise ValueError(
                "Start must be earlier than end."
            )

        if (
            start.minute != 0
            or start.second != 0
            or start.microsecond != 0
        ):
            raise ValueError(
                "Start must be aligned to a full hour."
            )

        if (
            end.minute != 0
            or end.second != 0
            or end.microsecond != 0
        ):
            raise ValueError(
                "End must be aligned to a full hour."
            )

        total_trades = 0
        total_candles = 0
        total_saved = 0
        days_processed = 0

        day_start = start

        while day_start < end:

            day_end = min(
                day_start + timedelta(days=1),
                end,
            )

            print(
                f"\nProcessing {day_start.date()} "
                f"({day_start.isoformat()} to {day_end.isoformat()})"
            )

            trades = self.provider.fetch_trades(
                start=day_start,
                end=day_end,
            )

            candles = self.aggregator.aggregate(trades)

            saved = self.repository.save_candles(
                candles=candles,
                timeframe=self.TIMEFRAME,
            )

            total_trades += len(trades)
            total_candles += len(candles)
            total_saved += saved
            days_processed += 1

            print(
                f"Trades: {len(trades):,} | "
                f"Hourly candles: {len(candles):,} | "
                f"Saved: {saved:,}"
            )

            day_start = day_end

        return {
            "exchange": self.exchange,
            "start": start,
            "end": end,
            "days_processed": days_processed,
            "trades_processed": total_trades,
            "candles_created": total_candles,
            "rows_saved": total_saved,
        }
