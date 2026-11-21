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
"""

from dataclasses import dataclass
from datetime import datetime, timezone
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
