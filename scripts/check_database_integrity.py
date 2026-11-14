
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def main():
    project_root = Path(__file__).resolve().parents[1]
    db_path = project_root / "database" / "market_data.db"

    symbol = "BTC/USD"
    market = "crypto"
    timeframe = "1h"

    print("DATABASE INTEGRITY REPORT")
    print("=========================")
    print(f"Database: {db_path}")
    print(f"Symbol: {symbol}")
    print(f"Timeframe: {timeframe}")
    print()

    with sqlite3.connect(db_path) as connection:

        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        rows = connection.execute("""
            SELECT
                exchange,
                timestamp,
                open,
                high,
                low,
                close,
                volume
            FROM market_candles
            WHERE symbol = ?
            AND market = ?
            AND timeframe = ?
            ORDER BY exchange, timestamp
        """, (symbol, market, timeframe)).fetchall()

        duplicate_groups = connection.execute("""
            SELECT COUNT(*)
            FROM (
                SELECT
                    exchange,
                    timestamp
                FROM market_candles
                WHERE symbol = ?
                AND market = ?
                AND timeframe = ?
                GROUP BY exchange, timestamp
                HAVING COUNT(*) > 1
            )
        """, (symbol, market, timeframe)).fetchone()[0]

        exchange_counts = connection.execute("""
            SELECT exchange, COUNT(*)
            FROM market_candles
            WHERE symbol = ?
            AND market = ?
            AND timeframe = ?
            GROUP BY exchange
            ORDER BY exchange
        """, (symbol, market, timeframe)).fetchall()

        total_records = connection.execute("""
            SELECT COUNT(*)
            FROM market_candles
        """).fetchone()[0]

    print(f"SQLite integrity: {integrity}")
    print(f"Total database records: {total_records:,}")
    print(f"Matching candles: {len(rows):,}")
    print(f"Duplicate exchange/timestamp groups: {duplicate_groups}")

    print()
    print("RECORDS PER EXCHANGE")
    print("--------------------")

    for exchange, count in exchange_counts:
        print(f"{exchange}: {count:,}")

    if not rows:
        print("\nNo matching candles found.")
        return

    candles_by_exchange = defaultdict(list)

    invalid_rows = 0
    non_aligned = 0
    empty_exchange = 0

    for row in rows:
        exchange, timestamp_text, open_price, high, low, close, volume = row

        if not exchange or not exchange.strip():
            empty_exchange += 1

        timestamp = datetime.fromisoformat(timestamp_text)

        if (
            timestamp.tzinfo is None
            or timestamp.utcoffset() is None
        ):
            invalid_rows += 1
            continue

        timestamp_utc = timestamp.astimezone(timezone.utc)

        if (
            timestamp_utc.minute != 0
            or timestamp_utc.second != 0
            or timestamp_utc.microsecond != 0
        ):
            non_aligned += 1

        values = [open_price, high, low, close, volume]

        if not all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            for value in values
        ):
            invalid_rows += 1
            continue

        if (
            min(open_price, high, low, close) <= 0
            or volume < 0
            or high < max(open_price, low, close)
            or low > min(open_price, high, close)
        ):
            invalid_rows += 1

        candles_by_exchange[exchange].append(timestamp_utc)

    print()
    print("EXCHANGE DATA QUALITY")
    print("---------------------")

    all_gaps = []

    for exchange, timestamps in sorted(candles_by_exchange.items()):

        timestamps.sort()

        if not timestamps:
            continue

        missing_candles = 0
        irregular_gaps = 0
        gaps = []

        for previous, current in zip(
            timestamps,
            timestamps[1:],
        ):
            difference = (
                current - previous
            ).total_seconds()

            if difference > 3600:

                if difference % 3600 == 0:
                    missing = int(difference / 3600) - 1
                    missing_candles += missing
                    gaps.append((previous, current, missing))
                else:
                    irregular_gaps += 1
                    gaps.append((previous, current, "irregular"))

        all_gaps.extend(
            (exchange, previous, current, missing)
            for previous, current, missing in gaps
        )

        print(f"\nExchange: {exchange}")
        print(f"Candles: {len(timestamps):,}")
        print(f"Earliest: {timestamps[0].isoformat()}")
        print(f"Latest: {timestamps[-1].isoformat()}")
        print(f"Missing hourly timestamps: {missing_candles:,}")
        print(f"Irregular gaps: {irregular_gaps}")

    print()
    print("OVERALL VALIDATION")
    print("------------------")
    print(f"Non-hour-aligned timestamps: {non_aligned}")
    print(f"Invalid OHLCV rows: {invalid_rows}")
    print(f"Empty exchange identifiers: {empty_exchange}")

    print()
    print("LARGEST DATA GAPS")
    print("-----------------")

    largest_gaps = sorted(
        [
            gap for gap in all_gaps
            if isinstance(gap[3], int)
        ],
        key=lambda gap: gap[3],
        reverse=True,
    )

    if not largest_gaps:
        print("No gaps detected.")
    else:
        for exchange, previous, current, missing in largest_gaps[:10]:
            print(
                f"{exchange}: "
                f"{previous.isoformat()} -> "
                f"{current.isoformat()} | Missing: {missing}"
            )

    print()
    print("VERIFICATION COMPLETE")


if __name__ == "__main__":
    main()
