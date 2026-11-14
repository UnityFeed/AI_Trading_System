import itertools
import sqlite3
from pathlib import Path


def main():

    project_root = Path(__file__).resolve().parents[1]
    db_path = project_root / "database" / "market_data.db"

    symbol = "BTC/USD"
    market = "crypto"
    timeframe = "1h"
    rows_per_pair = 5

    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")

    with sqlite3.connect(db_path) as connection:

        exchange_rows = connection.execute("""
            SELECT DISTINCT exchange
            FROM market_candles
            WHERE symbol = ?
            AND market = ?
            AND timeframe = ?
            ORDER BY exchange
        """, (symbol, market, timeframe)).fetchall()

        exchanges = [row[0] for row in exchange_rows]

        print("LARGEST EXCHANGE CLOSE-PRICE DIFFERENCES")
        print("========================================")
        print(f"Symbol: {symbol}")
        print(f"Timeframe: {timeframe}")

        for exchange_a, exchange_b in itertools.combinations(exchanges, 2):

            rows = connection.execute("""
                SELECT
                    a.timestamp,
                    a.open,
                    a.high,
                    a.low,
                    a.close,
                    a.volume,
                    b.open,
                    b.high,
                    b.low,
                    b.close,
                    b.volume,
                    ABS(a.close - b.close)
                        / ((a.close + b.close) / 2.0)
                        * 100.0 AS difference_percent
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
                ORDER BY difference_percent DESC
                LIMIT ?
            """, (
                exchange_a,
                exchange_b,
                symbol,
                market,
                timeframe,
                rows_per_pair,
            )).fetchall()

            print()
            print(f"{exchange_a} vs {exchange_b}")
            print("-" * (len(exchange_a) + len(exchange_b) + 4))

            for row in rows:
                (
                    timestamp,
                    a_open,
                    a_high,
                    a_low,
                    a_close,
                    a_volume,
                    b_open,
                    b_high,
                    b_low,
                    b_close,
                    b_volume,
                    difference_percent,
                ) = row

                print(
                    f"\n{timestamp}"
                    f"\n  Difference: {difference_percent:.6f}%"
                    f"\n  {exchange_a}: "
                    f"O={a_open} H={a_high} L={a_low} "
                    f"C={a_close} V={a_volume}"
                    f"\n  {exchange_b}: "
                    f"O={b_open} H={b_high} L={b_low} "
                    f"C={b_close} V={b_volume}"
                )

    print("\nInspection complete. The database was only read.")


if __name__ == "__main__":
    main()