"""
Show technical indicators on the primary history (Bitstamp before 2017,
Kraken from 2017) for 1h, 4h and 1d candles.

For each timeframe and segment it prints how many candles have every
indicator warmed up, and the latest values. 4h/1d candles are built in
memory from clean hourly candles; the database is only read.

Usage:
    python -m scripts.report_indicators
    python -m scripts.report_indicators path\\to\\other.db
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

from src.analysis.primary_history import get_primary_history
from src.analysis.technical_indicators import calculate_indicators
from src.analysis.timeframes import aggregate_hourly_candles, split_into_runs
from src.data_collection.market_data_repository import MarketDataRepository


HISTORY_START = datetime(2013, 1, 1, tzinfo=timezone.utc)
TIMEFRAMES = ("1h", "4h", "1d")


def fmt(value: float | None) -> str:
    if value is None:
        return "not warmed up"
    if abs(value) >= 100:
        return f"{value:,.2f}"
    return f"{value:.4f}"


def main(db_path: Path | None = None) -> None:

    repository = MarketDataRepository(db_path) if db_path else MarketDataRepository()

    # Only completed hours.
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    segments = get_primary_history(
        repository=repository, start=HISTORY_START, end=end
    )

    print("TECHNICAL INDICATORS: PRIMARY HISTORY")
    print("=====================================")
    print("Indicators restart at every gap and at the exchange switch.")
    print("A value stamped T uses candles up to and including period T,")
    print("so it is known when period T closes.")
    print()

    for timeframe in TIMEFRAMES:

        print(f"TIMEFRAME {timeframe}")
        print("-" * (10 + len(timeframe)))

        latest_row = None

        for segment in segments:

            candles = aggregate_hourly_candles(segment.candles, timeframe).candles
            rows = calculate_indicators(candles, timeframe)
            complete = sum(row.is_complete() for row in rows)
            runs = split_into_runs(candles, timeframe)

            print(
                f"{segment.exchange:<9} candles: {len(candles):>7,}  "
                f"runs: {len(runs):>5,}  fully warmed up: {complete:>7,}"
            )

            if rows:
                latest_row = rows[-1]

        if latest_row is not None:
            print()
            print(
                f"Latest {timeframe} candle: {latest_row.exchange} "
                f"{latest_row.timestamp.isoformat()}  close {fmt(latest_row.close)}"
            )
            for name, value in latest_row.values.items():
                print(f"  {name:<20} {fmt(value)}")

        print()

    print("Report complete. The database was only read.")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
