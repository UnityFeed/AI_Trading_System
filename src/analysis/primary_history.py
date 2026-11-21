"""
The project's primary BTC/USD price history.

Kraken is the primary exchange, but its data is only complete from
2017-01-01. Before that date Bitstamp is used instead (owner decision,
21 Nov 2026). The two exchanges are never merged into one series: the
history is returned as separate single-exchange segments. Analysis code
runs on each segment on its own, so the switch-over behaves like a gap
(windows and returns reset there, exactly as at any missing hour).

Each segment contains clean candles only (see get_clean_candles): the
exclusion list is applied and zero-volume filler candles are skipped.
Nothing in the database is changed or copied.

Two ways to read it:
- get_primary_history: separate single-exchange segments with real gaps.
  Use it for validation and anything that must reflect one exchange.
- get_continuous_history: one unbroken series in which missing hours are
  filled from other exchanges, with every substitution and every price
  jump between sources recorded (owner decision, 21 Nov 2026). Use it for
  indicators and research that need long uninterrupted history.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.analysis.market_data_quality import (
    DEFAULT_EXCLUSIONS_FILE,
    get_clean_candles,
)
from src.data_collection.market_data import MarketData
from src.data_collection.market_data_repository import MarketDataRepository


KRAKEN_PRIMARY_FROM = datetime(2017, 1, 1, tzinfo=timezone.utc)

# (exchange, from inclusive, until exclusive); None means open-ended.
PRIMARY_HISTORY_PLAN = (
    ("bitstamp", None, KRAKEN_PRIMARY_FROM),
    ("kraken", KRAKEN_PRIMARY_FROM, None),
)


@dataclass(frozen=True)
class HistorySegment:
    exchange: str
    start: datetime  # inclusive
    end: datetime  # exclusive
    candles: list[MarketData]


def get_primary_history(
    repository: MarketDataRepository,
    start: datetime,
    end: datetime,
    symbol: str = "BTC/USD",
    market: str = "crypto",
    timeframe: str = "1h",
    exclusions_file: str | Path = DEFAULT_EXCLUSIONS_FILE,
) -> list[HistorySegment]:
    """
    Return the primary history between start (inclusive) and end
    (exclusive) as a list of single-exchange segments, oldest first.

    Only segments that overlap the requested window are returned.
    """

    for value in (start, end):
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError("Start and end must be timezone-aware.")

    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)

    if start >= end:
        raise ValueError("Start time must be earlier than end time.")

    segments = []

    for exchange, plan_from, plan_until in PRIMARY_HISTORY_PLAN:

        segment_start = start if plan_from is None else max(start, plan_from)
        segment_end = end if plan_until is None else min(end, plan_until)

        if segment_start >= segment_end:
            continue

        candles = get_clean_candles(
            repository=repository,
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            start=segment_start,
            end=segment_end,
            exchange=exchange,
            exclusions_file=exclusions_file,
        )

        segments.append(
            HistorySegment(
                exchange=exchange,
                start=segment_start,
                end=segment_end,
                candles=candles,
            )
        )

    return segments


# ---------------------------------------------------------------------------
# Continuous history (owner decision 21 Nov 2026)
# ---------------------------------------------------------------------------
#
# One unbroken series from the first Bitstamp hour to the latest Kraken
# hour, so indicators can run from start to finish. Hours the primary
# exchange does not have (outages, excluded bad candles, zero-volume
# filler) are taken from another exchange, in FILL_ORDER. Every candle
# records which exchange it really came from, and every change of source
# is recorded with its price jump so large differences stay visible.
#
# The series is built in memory only. Candles are relabelled with the
# exchange name "primary" so the single-exchange checks in the analysis
# code accept them; the true source is in ContinuousHistory.sources.
#
# Substituted candles are NOT Kraken prices. A backtest must not fill an
# order on a substituted hour (Kraken was down, nobody could trade there).

PRIMARY_LABEL = "primary"

FILL_ORDER = {
    "bitstamp": ("coinbase", "kraken"),
    "kraken": ("coinbase", "bitstamp"),
}

LARGE_JUMP_PCT = 1.0

_HOUR = timedelta(hours=1)


@dataclass(frozen=True)
class SourceChange:
    """The price step where the series switches from one exchange to another."""

    timestamp: datetime  # first hour from the new source
    from_exchange: str
    to_exchange: str
    previous_close: float
    open: float

    @property
    def jump_pct(self) -> float:
        return (self.open / self.previous_close - 1.0) * 100.0


@dataclass(frozen=True)
class ContinuousHistory:
    candles: list[MarketData]  # exchange == PRIMARY_LABEL, oldest first
    sources: dict[datetime, str]  # timestamp -> real exchange
    primary_by_hour: dict[datetime, str]  # timestamp -> exchange that should have provided it
    source_changes: list[SourceChange]
    unfilled_hours: list[datetime]  # no exchange had a clean candle

    def is_substituted(self, timestamp: datetime) -> bool:
        return self.sources[timestamp] != self.primary_by_hour[timestamp]

    def substituted_hours(self) -> list[datetime]:
        return [c.timestamp for c in self.candles if self.is_substituted(c.timestamp)]

    def large_jumps(self, threshold_pct: float = LARGE_JUMP_PCT) -> list[SourceChange]:
        return [
            change for change in self.source_changes
            if abs(change.jump_pct) > threshold_pct
        ]

    def periods_with_substitutes(self, timeframe: str) -> set[datetime]:
        """Start of every 1h/4h/1d period that contains a substituted hour."""
        from src.analysis.timeframes import period_start

        return {
            period_start(timestamp, timeframe)
            for timestamp in self.substituted_hours()
        }


def _missing_ranges(present: dict, first: datetime, last: datetime) -> list[tuple[datetime, datetime]]:
    """Stretches of hours in [first, last] that are not in `present`, as (start, end) pairs."""
    ranges = []
    hour = first
    while hour <= last:
        if hour not in present:
            if ranges and ranges[-1][1] == hour:
                ranges[-1] = (ranges[-1][0], hour + _HOUR)
            else:
                ranges.append((hour, hour + _HOUR))
        hour += _HOUR
    return ranges


def get_continuous_history(
    repository: MarketDataRepository,
    start: datetime,
    end: datetime,
    symbol: str = "BTC/USD",
    market: str = "crypto",
    exclusions_file: str | Path = DEFAULT_EXCLUSIONS_FILE,
) -> ContinuousHistory:
    """
    Build the continuous hourly history between start and end.

    Each primary-history segment runs from its exchange's first to its last
    clean candle inside the window; missing hours in between are filled
    from FILL_ORDER. Hours no exchange has stay missing (unfilled_hours).
    """

    segments = get_primary_history(
        repository=repository,
        start=start,
        end=end,
        symbol=symbol,
        market=market,
        exclusions_file=exclusions_file,
    )

    candles: list[MarketData] = []
    sources: dict[datetime, str] = {}
    primary_by_hour: dict[datetime, str] = {}
    unfilled: list[datetime] = []

    for segment in segments:

        if not segment.candles:
            continue

        by_exchange = {
            segment.exchange: {c.timestamp: c for c in segment.candles}
        }

        hour = segment.candles[0].timestamp
        last = segment.candles[-1].timestamp

        # Only the hours the primary exchange lacks are looked up on the
        # other exchanges (a few hundred hours instead of their full history).
        missing_ranges = _missing_ranges(by_exchange[segment.exchange], hour, last)
        for fill_exchange in FILL_ORDER[segment.exchange]:
            found = {}
            for range_start, range_end in missing_ranges:
                for candle in get_clean_candles(
                    repository=repository,
                    symbol=symbol,
                    market=market,
                    timeframe="1h",
                    start=range_start,
                    end=range_end,
                    exchange=fill_exchange,
                    exclusions_file=exclusions_file,
                ):
                    found[candle.timestamp] = candle
            by_exchange[fill_exchange] = found

        order = (segment.exchange,) + FILL_ORDER[segment.exchange]

        while hour <= last:
            for exchange in order:
                candle = by_exchange[exchange].get(hour)
                if candle is not None:
                    candles.append(replace(candle, exchange=PRIMARY_LABEL))
                    sources[hour] = exchange
                    primary_by_hour[hour] = segment.exchange
                    break
            else:
                unfilled.append(hour)

            hour += _HOUR

    changes = []

    for previous, candle in zip(candles, candles[1:]):
        before = sources[previous.timestamp]
        after = sources[candle.timestamp]

        if before != after and candle.timestamp - previous.timestamp == _HOUR:
            changes.append(
                SourceChange(
                    timestamp=candle.timestamp,
                    from_exchange=before,
                    to_exchange=after,
                    previous_close=previous.close,
                    open=candle.open,
                )
            )

    return ContinuousHistory(
        candles=candles,
        sources=sources,
        primary_by_hour=primary_by_hour,
        source_changes=changes,
        unfilled_hours=unfilled,
    )
