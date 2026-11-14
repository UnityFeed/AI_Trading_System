from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.data_collection.market_data import MarketData


@dataclass(frozen=True)
class SimpleMovingAverage:
    exchange: str
    symbol: str
    timestamp: datetime
    period_hours: int
    value: float


def calculate_hourly_sma(
    candles: list[MarketData],
    period_hours: int,
) -> list[SimpleMovingAverage]:
    """
    Calculate a simple moving average from hourly candle closes.

    The rolling window resets when there is a missing or excluded hour.
    Candles must belong to one exchange and one symbol.
    """

    if (
        isinstance(period_hours, bool)
        or not isinstance(period_hours, int)
        or period_hours < 1
    ):
        raise ValueError("period_hours must be a positive integer.")

    if not candles:
        return []

    ordered_candles = sorted(
        candles,
        key=lambda candle: candle.timestamp,
    )

    first = ordered_candles[0]
    rolling_closes = deque(maxlen=period_hours)
    averages = []
    previous = None

    for candle in ordered_candles:

        if (
            candle.timestamp.tzinfo is None
            or candle.timestamp.utcoffset() is None
        ):
            raise ValueError(
                "All candle timestamps must be timezone-aware."
            )

        if candle.exchange.lower() != first.exchange.lower():
            raise ValueError(
                "Calculate an SMA for one exchange at a time."
            )

        if candle.symbol != first.symbol:
            raise ValueError(
                "Calculate an SMA for one symbol at a time."
            )

        if candle.close <= 0:
            raise ValueError("Candle closes must be greater than zero.")

        if previous is not None:
            elapsed = candle.timestamp - previous.timestamp

            if elapsed <= timedelta(0):
                raise ValueError(
                    "Duplicate candle timestamps were found."
                )

            if elapsed != timedelta(hours=1):
                rolling_closes.clear()

        rolling_closes.append(candle.close)

        if len(rolling_closes) == period_hours:
            averages.append(
                SimpleMovingAverage(
                    exchange=candle.exchange,
                    symbol=candle.symbol,
                    timestamp=candle.timestamp,
                    period_hours=period_hours,
                    value=sum(rolling_closes) / period_hours,
                )
            )

        previous = candle

    return averages