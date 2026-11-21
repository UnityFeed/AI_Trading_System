from dataclasses import dataclass
from datetime import timedelta

from src.analysis.timeframes import TIMEFRAME_HOURS
from src.data_collection.market_data import MarketData


@dataclass(frozen=True)
class PriceReturn:
    exchange: str
    symbol: str
    previous_timestamp: object
    timestamp: object
    previous_close: float
    close: float
    return_pct: float


def calculate_hourly_returns(
    candles: list[MarketData],
) -> list[PriceReturn]:
    """
    Calculate close-to-close returns for consecutive hourly candles.

    Candles must belong to one exchange and one symbol.
    Returns across missing or excluded hours are skipped.
    """

    return calculate_returns(candles, "1h")


def calculate_returns(
    candles: list[MarketData],
    timeframe: str,
) -> list[PriceReturn]:
    """
    Calculate close-to-close returns for consecutive candles of one
    timeframe ("1h", "4h" or "1d").

    Candles must belong to one exchange and one symbol.
    Returns across missing or skipped periods are skipped.
    """

    if timeframe not in TIMEFRAME_HOURS:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    step = timedelta(hours=TIMEFRAME_HOURS[timeframe])

    if not candles:
        return []

    ordered_candles = sorted(
        candles,
        key=lambda candle: candle.timestamp,
    )

    first = ordered_candles[0]

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
                "Calculate returns for one exchange at a time."
            )

        if candle.symbol != first.symbol:
            raise ValueError(
                "Calculate returns for one symbol at a time."
            )

    returns = []
    previous = None

    for candle in ordered_candles:

        if previous is not None:
            elapsed = candle.timestamp - previous.timestamp

            if elapsed == step:
                if previous.close <= 0:
                    raise ValueError(
                        "Previous candle close must be greater than zero."
                    )

                return_pct = (
                    (candle.close / previous.close) - 1.0
                ) * 100.0

                returns.append(
                    PriceReturn(
                        exchange=candle.exchange,
                        symbol=candle.symbol,
                        previous_timestamp=previous.timestamp,
                        timestamp=candle.timestamp,
                        previous_close=previous.close,
                        close=candle.close,
                        return_pct=return_pct,
                    )
                )

        previous = candle

    return returns