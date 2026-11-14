import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def main():

    project_root = Path(__file__).resolve().parents[1]
    csv_path = (
        project_root
        / "data"
        / "historical"
        / "extracted"
        / "XBTUSD_60.csv"
    )
    db_path = project_root / "database" / "market_data.db"

    target = datetime(
        2013, 11, 10, 4, 0,
        tzinfo=timezone.utc,
    )
    target_unix = int(target.timestamp())

    if not csv_path.is_file():
        raise FileNotFoundError(f"Kraken CSV not found: {csv_path}")

    print(f"Target candle: {target.isoformat()}")
    print(f"Unix timestamp: {target_unix}")
    print()

    print("ORIGINAL KRAKEN CSV ROW")
    print("========================")

    found_in_csv = False

    with csv_path.open("r", newline="", encoding="utf-8") as file:
        for line_number, row in enumerate(csv.reader(file), start=1):
            if row and int(float(row[0])) == target_unix:
                print(f"CSV line {line_number}: {row}")
                found_in_csv = True

    if not found_in_csv:
        print("No matching row found in the CSV.")

    print()
    print("DATABASE ROW")
    print("============")

    with sqlite3.connect(db_path) as connection:
        row = connection.execute("""
            SELECT
                exchange,
                timestamp,
                open,
                high,
                low,
                close,
                volume
            FROM market_candles
            WHERE exchange = 'kraken'
            AND symbol = 'BTC/USD'
            AND market = 'crypto'
            AND timeframe = '1h'
            AND timestamp = ?
        """, (target.isoformat(),)).fetchone()

    if row:
        print(row)
    else:
        print("No matching Kraken row found in the database.")

    print()
    print("Inspection complete. The files and database were only read.")


if __name__ == "__main__":
    main()