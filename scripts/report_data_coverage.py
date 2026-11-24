"""
Per-exchange, per-year coverage report for hourly BTC/USD candles.

For each exchange and calendar year (UTC) it shows:
- expected hours (between that exchange's first and last stored candle)
- stored candles and missing hours
- zero-volume candles: hours where the exchange reported no trades
- flat zero-volume candles: open = high = low = close and volume = 0,
  which usually means the exchange filled the hour itself instead of
  leaving a gap (no trading took place in that hour)

It also lists the longest runs of consecutive zero-volume hours, which
point at exchange outages or periods without trading.

The database is opened read-only; nothing is changed.
"""

import sqlite3
from contextlib import closing
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


SYMBOL = "BTC/USD"
MARKET = "crypto"
TIMEFRAME = "1h"
HOUR = timedelta(hours=1)
LONGEST_RUNS_TO_SHOW = 5


def parse_utc(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def year_hours(first: datetime, last: datetime) -> dict[int, int]:
    """Number of expected hourly candles per year between first and last."""

    counts = {}

    for year in range(first.year, last.year + 1):
        year_start = max(first, datetime(year, 1, 1, tzinfo=timezone.utc))
        next_year = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        year_end = min(last + HOUR, next_year)
        counts[year] = int((year_end - year_start) / HOUR)

    return counts


def report_exchange(exchange: str, rows: list[tuple]) -> None:

    first = parse_utc(rows[0][0])
    last = parse_utc(rows[-1][0])
    expected = year_hours(first, last)

    stored = defaultdict(int)
    zero_volume = defaultdict(int)
    flat_zero_volume = defaultdict(int)

    runs = []
    run_start = None
    run_length = 0
    previous = None

    for timestamp_text, open_, high, low, close, volume in rows:

        timestamp = parse_utc(timestamp_text)
        year = timestamp.year
        stored[year] += 1

        is_zero = volume == 0

        if is_zero:
            zero_volume[year] += 1

            if open_ == high == low == close:
                flat_zero_volume[year] += 1

        # A zero-volume run continues only across consecutive hours.
        continues = (
            is_zero
            and run_start is not None
            and previous is not None
            and timestamp - previous == HOUR
        )

        if continues:
            run_length += 1
        else:
            if run_start is not None:
                runs.append((run_length, run_start))
            run_start, run_length = (timestamp, 1) if is_zero else (None, 0)

        previous = timestamp

    if run_start is not None:
        runs.append((run_length, run_start))

    print(exchange.upper())
    print("-" * len(exchange))
    print(f"First: {first.isoformat()}  Last: {last.isoformat()}")
    print()
    print(
        f"{'Year':<6}{'Expected':>10}{'Stored':>10}{'Missing':>10}"
        f"{'ZeroVol':>10}{'FlatZero':>10}"
    )

    totals = [0, 0, 0, 0, 0]

    for year in sorted(expected):
        values = [
            expected[year],
            stored[year],
            expected[year] - stored[year],
            zero_volume[year],
            flat_zero_volume[year],
        ]
        totals = [t + v for t, v in zip(totals, values)]

        print(f"{year:<6}" + "".join(f"{v:>10,}" for v in values))

    print(f"{'Total':<6}" + "".join(f"{v:>10,}" for v in totals))
    print()

    longest = sorted(runs, reverse=True)[:LONGEST_RUNS_TO_SHOW]

    if longest:
        print("Longest runs of consecutive zero-volume hours:")
        for length, start in longest:
            end = start + HOUR * (length - 1)
            print(f"  {length:>5} h  {start.isoformat()} -> {end.isoformat()}")
    else:
        print("No zero-volume candles.")

    print()


def main(db_path: Path | None = None) -> None:

    if db_path is None:
        project_root = Path(__file__).resolve().parents[1]
        db_path = project_root / "database" / "market_data.db"

    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")

    print("DATA COVERAGE REPORT")
    print("====================")
    print(f"Database: {db_path}")
    print(f"Symbol: {SYMBOL}  Timeframe: {TIMEFRAME}")
    print()

    # mode=ro opens the file read-only, so this script cannot change it.
    uri = f"{db_path.resolve().as_uri()}?mode=ro"

    with closing(sqlite3.connect(uri, uri=True)) as connection:

        exchanges = [
            row[0]
            for row in connection.execute(
                """
                SELECT DISTINCT exchange FROM market_candles
                WHERE symbol = ? AND market = ? AND timeframe = ?
                ORDER BY exchange
                """,
                (SYMBOL, MARKET, TIMEFRAME),
            )
        ]

        for exchange in exchanges:
            rows = connection.execute(
                """
                SELECT timestamp, open, high, low, close, volume
                FROM market_candles
                WHERE exchange = ? AND symbol = ? AND market = ?
                AND timeframe = ?
                ORDER BY timestamp
                """,
                (exchange, SYMBOL, MARKET, TIMEFRAME),
            ).fetchall()

            if rows:
                report_exchange(exchange, rows)

    print("Report complete. The database was only read.")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
