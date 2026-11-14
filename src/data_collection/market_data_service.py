
from datetime import datetime

from src.data_collection.market_data import MarketData
from src.data_collection.data_validator import validate_market_data
from src.data_collection.market_data_provider import MarketDataProvider


class MarketDataService:

    def __init__(self, provider: MarketDataProvider):
        self.provider = provider

    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[MarketData]:

        if (
            start.tzinfo is None
            or start.utcoffset() is None
            or end.tzinfo is None
            or end.utcoffset() is None
        ):
            raise ValueError("Start and end must be timezone-aware.")

        if start >= end:
            raise ValueError("Start time must be earlier than end time.")

        candles = self.provider.fetch_candles(
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
        )

        if not isinstance(candles, list):
            raise TypeError("Provider must return a list of candles.")

        previous_timestamp = None
        provider_exchange = getattr(
            self.provider,
            "exchange",
            None,
        )

        for index, candle in enumerate(candles):

            errors = validate_market_data(candle)

            if errors:
                raise ValueError(
                    f"Invalid candle at index {index}: "
                    f"{'; '.join(errors)}"
                )

            if candle.symbol != symbol:
                raise ValueError(
                    f"Unexpected symbol at index {index}: {candle.symbol}"
                )

            if provider_exchange is not None:
                if candle.exchange.lower() != provider_exchange.lower():
                    raise ValueError(
                        f"Unexpected exchange at index {index}: "
                        f"{candle.exchange}. "
                        f"Expected {provider_exchange}."
                    )

            if candle.timestamp < start or candle.timestamp >= end:
                raise ValueError(
                    f"Candle timestamp outside requested time range "
                    f"at index {index}."
                )

            if (
                previous_timestamp is not None
                and candle.timestamp <= previous_timestamp
            ):
                raise ValueError(
                    "Candles must be ordered by timestamp, oldest first, "
                    "without duplicate timestamps."
                )

            previous_timestamp = candle.timestamp

        return candles
