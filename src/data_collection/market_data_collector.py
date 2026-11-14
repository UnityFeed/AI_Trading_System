
from datetime import datetime, timedelta, timezone

from src.data_collection.market_data_service import MarketDataService
from src.data_collection.market_data_repository import MarketDataRepository


class MarketDataCollector:
    """
    Collects new completed BTC/USD hourly candles from Kraken.

    This collector handles forward collection only.
    Historical gap recovery is handled separately.
    """

    EXCHANGE = "kraken"
    SYMBOL = "BTC/USD"
    MARKET = "crypto"
    TIMEFRAME = "1h"

    CANDLE_DURATION = timedelta(hours=1)
    MAX_FETCH_HOURS = 700

    def __init__(
        self,
        market_data_service: MarketDataService,
        repository: MarketDataRepository,
    ):
        self.market_data_service = market_data_service
        self.repository = repository

    def collect(
        self,
        end: datetime,
        initial_start: datetime | None = None,
    ) -> dict:

        if (
            not isinstance(end, datetime)
            or end.tzinfo is None
            or end.utcoffset() is None
        ):
            raise ValueError("End time must be a timezone-aware datetime.")

        end = end.astimezone(timezone.utc)
        end = end.replace(minute=0, second=0, microsecond=0)

        latest = self.repository.get_latest_candle_timestamp(
            symbol=self.SYMBOL,
            market=self.MARKET,
            timeframe=self.TIMEFRAME,
            exchange=self.EXCHANGE,
        )

        if latest is None:

            if (
                not isinstance(initial_start, datetime)
                or initial_start.tzinfo is None
                or initial_start.utcoffset() is None
            ):
                raise ValueError(
                    "An initial_start time is required when the database "
                    "does not contain any candles."
                )

            start = initial_start.astimezone(timezone.utc)

        else:
            start = latest.astimezone(timezone.utc) + self.CANDLE_DURATION

        if (
            start.minute != 0
            or start.second != 0
            or start.microsecond != 0
        ):
            raise ValueError("Start time must be aligned to a full hour.")

        if start >= end:
            return {
                "exchange": self.EXCHANGE,
                "start": start,
                "end": end,
                "fetched": 0,
                "saved": 0,
                "unreturned_hours": 0,
            }

        total_hours = int(
            (end - start) / self.CANDLE_DURATION
        )

        if total_hours > self.MAX_FETCH_HOURS:
            raise RuntimeError(
                f"{total_hours} hours of data are missing. "
                f"The normal Kraken collector supports a maximum of "
                f"{self.MAX_FETCH_HOURS} hours per run. "
                "Use the historical recovery process for larger gaps."
            )

        candles = self.market_data_service.get_candles(
            symbol=self.SYMBOL,
            timeframe=self.TIMEFRAME,
            start=start,
            end=end,
        )

        saved_count = self.repository.save_candles(
            candles=candles,
            timeframe=self.TIMEFRAME,
        )

        returned_timestamps = {
            candle.timestamp.astimezone(timezone.utc)
            for candle in candles
        }

        expected_hours = set()
        timestamp = start

        while timestamp < end:
            expected_hours.add(timestamp)
            timestamp += self.CANDLE_DURATION

        unreturned_hours = len(
            expected_hours - returned_timestamps
        )

        return {
            "exchange": self.EXCHANGE,
            "start": start,
            "end": end,
            "fetched": len(candles),
            "saved": saved_count,
            "unreturned_hours": unreturned_hours,
        }
