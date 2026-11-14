
import sqlite3
from pathlib import Path

db_path = Path("database/market_data.db")

connection = sqlite3.connect(db_path)

result = connection.execute("""
    SELECT
        COUNT(*),
        MIN(timestamp),
        MAX(timestamp)
    FROM market_candles
    WHERE market = 'crypto'
    AND symbol = 'BTC/USD'
    AND timeframe = '1h'
""").fetchone()

connection.close()

print("Total candles:", result[0])
print("First candle:", result[1])
print("Latest candle:", result[2])
