from datetime import datetime, timedelta, timezone

from src.data_collection.market_data_service import MarketDataService
from src.data_collection.market_data_repository import MarketDataRepository


class MarketDataCollector:
    """
    Collects missing BTC/USD hourly candles and stores them in SQLite.
    """

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
        """
        Find and collect missing completed hourly candles.

        The end time is rounded down to the beginning of its hour.
        The end boundary itself is excluded.
        """

        if (
            not isinstance(end, datetime)
            or end.tzinfo is None
            or end.utcoffset() is None
        ):
            raise ValueError("End time must be a timezone-aware datetime.")

        end = end.astimezone(timezone.utc)

        # Exclude the currently forming hourly candle.
        end = end.replace(minute=0, second=0, microsecond=0)

        earliest = self.repository.get_earliest_candle_timestamp(
            symbol=self.SYMBOL,
            market=self.MARKET,
            timeframe=self.TIMEFRAME,
        )

        if earliest is None:

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
            start = earliest.astimezone(timezone.utc)

        if (
            start.minute != 0
            or start.second != 0
            or start.microsecond != 0
        ):
            raise ValueError("Start time must be aligned to a full hour.")

        if start >= end:
            return {
                "start": start,
                "end": end,
                "fetched": 0,
                "saved": 0,
                "missing_remaining": 0,
            }

        existing_timestamps = set(
            self.repository.get_candle_timestamps(
                symbol=self.SYMBOL,
                market=self.MARKET,
                timeframe=self.TIMEFRAME,
                start=start,
                end=end,
            )
        )

        expected_timestamps = set()
        timestamp = start

        while timestamp < end:
            expected_timestamps.add(timestamp)
            timestamp += self.CANDLE_DURATION

        missing_timestamps = expected_timestamps - existing_timestamps

        fetched_count = 0
        saved_count = 0

        # Fetch in chunks to stay below Kraken's 720-candle limit.
        chunk_start = start

        while chunk_start < end:

            chunk_end = min(
                chunk_start + self.MAX_FETCH_HOURS * self.CANDLE_DURATION,
                end,
            )

            chunk_missing = {
                timestamp
                for timestamp in missing_timestamps
                if chunk_start <= timestamp < chunk_end
            }

            if chunk_missing:

                candles = self.market_data_service.get_candles(
                    symbol=self.SYMBOL,
                    timeframe=self.TIMEFRAME,
                    start=chunk_start,
                    end=chunk_end,
                )

                fetched_count += len(candles)

                candles_to_save = [
                    candle
                    for candle in candles
                    if candle.timestamp.astimezone(timezone.utc)
                    in chunk_missing
                ]

                saved_count += self.repository.save_candles(
                    candles=candles_to_save,
                    timeframe=self.TIMEFRAME,
                )

            chunk_start = chunk_end

        remaining_timestamps = set(
            self.repository.get_candle_timestamps(
                symbol=self.SYMBOL,
                market=self.MARKET,
                timeframe=self.TIMEFRAME,
                start=start,
                end=end,
            )
        )

        missing_remaining = len(
            expected_timestamps - remaining_timestamps
        )

        return {
            "start": start,
            "end": end,
            "fetched": fetched_count,
            "saved": saved_count,
            "missing_remaining": missing_remaining,
        }