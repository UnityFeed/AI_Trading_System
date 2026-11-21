"""
Build 4h and 1d candles from clean hourly candles.

Rules:
- Periods follow UTC boundaries. 4h candles start at 00, 04, 08, 12, 16
  and 20 UTC; daily candles start at 00:00 UTC. This matches how Kraken,
  Bitstamp and Coinbase define their own daily candles (checked against
  their live APIs on 21 Nov 2026).
- Only complete periods are built. If any hour of a period is missing or
  was excluded as bad data, that whole period is skipped and reported, so
  every derived candle is made of real hourly candles only. This also
  means the still-running current period is never returned.
- Candles from one exchange and one symbol at a time.

A derived candle is a normal MarketData whose timestamp is the start of
its period (the same convention as the hourly candles):
open = first hour's open, high = highest high, low = lowest low,
close = last hour's close, volume = sum of hourly volumes.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.data_collection.market_data import MarketData


TIMEFRAME_HOURS = {
    "1h": 1,
    "4h": 4,
    "1d": 24,
}

HOUR = timedelta(hours=1)


@dataclass(frozen=True)
class IncompletePeriod:
    start: datetime
    hours_present: int
    hours_expected: int


@dataclass(frozen=True)
class AggregationResult:
    timeframe: str
    candles: list[MarketData]
    incomplete_periods: list[IncompletePeriod]


def period_start(timestamp: datetime, timeframe: str) -> datetime:
    """Return the UTC start of the period that contains this hour."""

    hours = TIMEFRAME_HOURS[timeframe]
    utc = timestamp.astimezone(timezone.utc)

    return utc.replace(
        hour=utc.hour - utc.hour % hours,
        minute=0,
        second=0,
        microsecond=0,
    )


def _validate_candles(candles: list[MarketData]) -> list[MarketData]:
    """Sort and check: one exchange/symbol, tz-aware, hour-aligned, unique."""

    ordered = sorted(candles, key=lambda candle: candle.timestamp)
    first = ordered[0]
    previous = None

    for candle in ordered:

        if (
            candle.timestamp.tzinfo is None
            or candle.timestamp.utcoffset() is None
        ):
            raise ValueError("All candle timestamps must be timezone-aware.")

        if (
            candle.timestamp.minute
            or candle.timestamp.second
            or candle.timestamp.microsecond
        ):
            raise ValueError(
                f"Candle is not aligned to a full hour: "
                f"{candle.timestamp.isoformat()}"
            )

        if candle.exchange.lower() != first.exchange.lower():
            raise ValueError("Aggregate one exchange at a time.")

        if candle.symbol != first.symbol:
            raise ValueError("Aggregate one symbol at a time.")

        if previous is not None and candle.timestamp == previous.timestamp:
            raise ValueError(
                f"Duplicate candle timestamp: {candle.timestamp.isoformat()}"
            )

        previous = candle

    return ordered


def aggregate_hourly_candles(
    candles: list[MarketData],
    timeframe: str,
) -> AggregationResult:
    """
    Combine clean hourly candles into complete candles of a longer
    timeframe ("1h", "4h" or "1d").
    """

    if timeframe not in TIMEFRAME_HOURS:
        raise ValueError(
            f"Unsupported timeframe: {timeframe}. "
            f"Use one of: {', '.join(TIMEFRAME_HOURS)}"
        )

    if not candles:
        return AggregationResult(timeframe, [], [])

    hours_expected = TIMEFRAME_HOURS[timeframe]
    ordered = _validate_candles(candles)

    # Group the hours by the period they belong to (in time order).
    periods: dict[datetime, list[MarketData]] = {}

    for candle in ordered:
        periods.setdefault(
            period_start(candle.timestamp, timeframe), []
        ).append(candle)

    derived = []
    incomplete = []

    for start, hours in periods.items():

        if len(hours) != hours_expected:
            incomplete.append(
                IncompletePeriod(
                    start=start,
                    hours_present=len(hours),
                    hours_expected=hours_expected,
                )
            )
            continue

        first, last = hours[0], hours[-1]

        derived.append(
            MarketData(
                exchange=first.exchange,
                symbol=first.symbol,
                market=first.market,
                timestamp=start,
                open=first.open,
                high=max(candle.high for candle in hours),
                low=min(candle.low for candle in hours),
                close=last.close,
                volume=sum(candle.volume for candle in hours),
            )
        )

    return AggregationResult(
        timeframe=timeframe,
        candles=derived,
        incomplete_periods=incomplete,
    )


def split_into_runs(
    candles: list[MarketData],
    timeframe: str,
) -> list[list[MarketData]]:
    """
    Split candles of one timeframe into runs of consecutive candles.

    A new run starts wherever the next candle is not exactly one period
    after the previous one (a missing, excluded or skipped period).
    Indicators are calculated per run, so no value is ever computed
    across a gap.
    """

    if timeframe not in TIMEFRAME_HOURS:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    if not candles:
        return []

    step = timedelta(hours=TIMEFRAME_HOURS[timeframe])
    ordered = _validate_candles(candles)

    for candle in ordered:
        if period_start(candle.timestamp, timeframe) != candle.timestamp:
            raise ValueError(
                f"Candle at {candle.timestamp.isoformat()} does not start "
                f"a {timeframe} period."
            )

    runs = [[ordered[0]]]

    for previous, candle in zip(ordered, ordered[1:]):
        if candle.timestamp - previous.timestamp == step:
            runs[-1].append(candle)
        else:
            runs.append([candle])

    return runs
