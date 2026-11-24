"""
Show technical indicators on the continuous history (Bitstamp before 2017,
Kraken from 2017, gaps filled from the other exchanges) for 1h, 4h and 1d.

For each timeframe it prints how many candles have every indicator warmed
up, and the latest values. 4h/1d candles are built in
memory from clean hourly candles; the database is only read.

Usage:
    python -m scripts.report_indicators
    python -m scripts.report_indicators path\\to\\other.db
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.analysis.primary_history import get_trading_history
from src.analysis.technical_indicators import calculate_indicators
from src.analysis.timeframes import (
    TIMEFRAME_HOURS,
    aggregate_hourly_candles,
    split_into_runs,
)
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

    history = get_trading_history(
        repository=repository, start=HISTORY_START, end=end
    )

    print("TECHNICAL INDICATORS: CONTINUOUS HISTORY")
    print("========================================")
    print("Bitstamp before 2017, Kraken from 2017; gaps filled from the other")
    print("exchanges (see scripts.report_continuous_history). Indicators only")
    print("restart where no exchange has data. A value stamped T uses candles")
    print("up to and including period T, so it is known when period T closes.")
    print()

    for timeframe in TIMEFRAMES:

        print(f"TIMEFRAME {timeframe}")
        print("-" * (10 + len(timeframe)))

        candles = aggregate_hourly_candles(history.candles, timeframe).candles
        rows = calculate_indicators(candles, timeframe)
        complete = sum(row.is_complete() for row in rows)
        runs = split_into_runs(candles, timeframe)

        print(
            f"candles: {len(candles):,}  runs: {len(runs):,}  "
            f"fully warmed up: {complete:,}"
        )

        if rows:
            latest = rows[-1]
            last_hour = latest.timestamp + timedelta(
                hours=TIMEFRAME_HOURS[timeframe] - 1
            )
            source = history.sources[last_hour]
            print()
            print(
                f"Latest {timeframe} candle: {latest.timestamp.isoformat()}  "
                f"close {fmt(latest.close)}  (last hour from {source})"
            )
            for name, value in latest.values.items():
                print(f"  {name:<20} {fmt(value)}")

        print()

    print("Report complete. The database was only read.")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
