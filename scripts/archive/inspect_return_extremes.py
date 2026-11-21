import csv
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


RETURN_TIMES = (
    datetime(2014, 9, 18, 20, 0, tzinfo=timezone.utc),
    datetime(2015, 11, 3, 10, 0, tzinfo=timezone.utc),
)


def main():

    project_root = Path(__file__).resolve().parents[2]  # scripts/archive/ -> project root
    csv_path = (
        project_root
        / "data"
        / "historical"
        / "extracted"
        / "XBTUSD_60.csv"
    )
    db_path = project_root / "database" / "market_data.db"

    if not csv_path.is_file():
        raise FileNotFoundError(f"Kraken CSV not found: {csv_path}")

    check_times = set()

    for return_time in RETURN_TIMES:
        check_times.add(return_time - timedelta(hours=1))
        check_times.add(return_time)

    unix_timestamps = {
        int(timestamp.timestamp()): timestamp
        for timestamp in check_times
    }

    source_rows = {}

    with csv_path.open("r", newline="", encoding="utf-8") as file:
        for row in csv.reader(file):
            if row:
                source_timestamp = int(float(row[0]))

                if source_timestamp in unix_timestamps:
                    source_rows[source_timestamp] = row

    with sqlite3.connect(db_path) as connection:

        print("INSPECTING EXTREME HOURLY RETURNS")
        print("=================================")

        for return_time in RETURN_TIMES:
            previous_time = return_time - timedelta(hours=1)

            print()
            print(f"Return ending at: {return_time.isoformat()}")
            print(
                f"Previous candle time: "
                f"{previous_time.isoformat()}"
            )

            for timestamp in (previous_time, return_time):
                unix_timestamp = int(timestamp.timestamp())

                print()
                print(f"Hour: {timestamp.isoformat()}")

                source_row = source_rows.get(unix_timestamp)

                if source_row:
                    print(f"Kraken source CSV row: {source_row}")
                else:
                    print("No matching Kraken CSV row found.")

                rows = connection.execute("""
                    SELECT
                        exchange,
                        open,
                        high,
                        low,
                        close,
                        volume
                    FROM market_candles
                    WHERE symbol = 'BTC/USD'
                    AND market = 'crypto'
                    AND timeframe = '1h'
                    AND timestamp = ?
                    ORDER BY exchange
                """, (timestamp.isoformat(),)).fetchall()

                if not rows:
                    print("No matching database candles found.")
                else:
                    for row in rows:
                        print(f"Database: {row}")

    print()
    print("Inspection complete. The CSV and database were only read.")


if __name__ == "__main__":
    main()