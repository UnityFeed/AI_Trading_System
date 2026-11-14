import itertools
import sqlite3
from pathlib import Path


def main():

    project_root = Path(__file__).resolve().parents[1]
    db_path = project_root / "database" / "market_data.db"

    symbol = "BTC/USD"
    market = "crypto"
    timeframe = "1h"

    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")

    with sqlite3.connect(db_path) as connection:

        exchange_rows = connection.execute("""
            SELECT
                exchange,
                COUNT(*),
                MIN(timestamp),
                MAX(timestamp)
            FROM market_candles
            WHERE symbol = ?
            AND market = ?
            AND timeframe = ?
            GROUP BY exchange
            ORDER BY exchange
        """, (symbol, market, timeframe)).fetchall()

        exchanges = [row[0] for row in exchange_rows]

        print("EXCHANGE DATA SUMMARY")
        print("=====================")
        print(f"Symbol: {symbol}")
        print(f"Timeframe: {timeframe}")
        print()

        for exchange, count, earliest, latest in exchange_rows:
            print(f"{exchange}: {count:,} candles")
            print(f"  Earliest: {earliest}")
            print(f"  Latest:   {latest}")

        print()
        print("PAIRWISE CLOSE-PRICE COMPARISON")
        print("===============================")

        for exchange_a, exchange_b in itertools.combinations(exchanges, 2):

            result = connection.execute("""
                SELECT
                    COUNT(*),
                    MIN(a.timestamp),
                    MAX(a.timestamp),
                    AVG(
                        ABS(a.close - b.close)
                        / ((a.close + b.close) / 2.0)
                        * 100.0
                    ),
                    MAX(
                        ABS(a.close - b.close)
                        / ((a.close + b.close) / 2.0)
                        * 100.0
                    )
                FROM market_candles AS a
                JOIN market_candles AS b
                    ON a.timestamp = b.timestamp
                    AND a.symbol = b.symbol
                    AND a.market = b.market
                    AND a.timeframe = b.timeframe
                WHERE a.exchange = ?
                AND b.exchange = ?
                AND a.symbol = ?
                AND a.market = ?
                AND a.timeframe = ?
            """, (
                exchange_a,
                exchange_b,
                symbol,
                market,
                timeframe,
            )).fetchone()

            overlap_count, first_shared, last_shared, avg_diff, max_diff = result

            print()
            print(f"{exchange_a} vs {exchange_b}")

            if overlap_count == 0:
                print("  No shared hourly timestamps found.")
                continue

            print(f"  Shared timestamps: {overlap_count:,}")
            print(f"  First shared:      {first_shared}")
            print(f"  Last shared:       {last_shared}")
            print(f"  Average close difference: {avg_diff:.6f}%")
            print(f"  Largest close difference: {max_diff:.6f}%")

    print()
    print("Comparison complete. The database was only read.")


if __name__ == "__main__":
    main()