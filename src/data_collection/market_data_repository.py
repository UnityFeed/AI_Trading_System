
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from src.data_collection.market_data import MarketData
from src.data_collection.data_validator import validate_market_data


class MarketDataRepository:
    """
    Stores and retrieves market candles using SQLite.
    """

    def __init__(self, db_path=None):

        if db_path is None:
            project_root = Path(__file__).resolve().parents[2]
            db_path = project_root / "database" / "market_data.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._initialize_database()

    def _initialize_database(self):

        with closing(sqlite3.connect(self.db_path)) as connection:
             with connection:
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS market_candles (
                        market TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        timeframe TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        open REAL NOT NULL,
                        high REAL NOT NULL,
                        low REAL NOT NULL,
                        close REAL NOT NULL,
                        volume REAL NOT NULL,

                        PRIMARY KEY (
                            market,
                            symbol,
                            timeframe,
                            timestamp
                        )
                    )
                """)

    def save_candles(
        self,
        candles: list[MarketData],
        timeframe: str,
    ) -> int:

        if not isinstance(timeframe, str) or not timeframe.strip():
            raise ValueError("Timeframe must be a non-empty string.")

        rows = []

        for candle in candles:

            errors = validate_market_data(candle)

            if errors:
                raise ValueError(
                    f"Cannot save invalid candle: {'; '.join(errors)}"
                )

            timestamp = candle.timestamp.astimezone(
                timezone.utc
            ).isoformat()

            rows.append((
                candle.market,
                candle.symbol,
                timeframe,
                timestamp,
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                candle.volume,
            ))

        with closing(sqlite3.connect(self.db_path)) as connection:
            with connection:
                connection.executemany("""
                    INSERT INTO market_candles (
                        market,
                        symbol,
                        timeframe,
                        timestamp,
                        open,
                        high,
                        low,
                        close,
                        volume
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)

                    ON CONFLICT (
                        market,
                        symbol,
                        timeframe,
                        timestamp
                    )
                    DO UPDATE SET
                        open = excluded.open,
                        high = excluded.high,
                        low = excluded.low,
                        close = excluded.close,
                        volume = excluded.volume
                """, rows)
        return len(rows)

    def get_candles(
        self,
        symbol: str,
        market: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[MarketData]:

        if (
            start.tzinfo is None
            or start.utcoffset() is None
            or end.tzinfo is None
            or end.utcoffset() is None
        ):
            raise ValueError("Start and end must be timezone-aware.")

        if start >= end:
            raise ValueError("Start time must be earlier than end time.")

        start_utc = start.astimezone(timezone.utc).isoformat()
        end_utc = end.astimezone(timezone.utc).isoformat()

        with closing(sqlite3.connect(self.db_path)) as connection:
            with connection:
                cursor = connection.execute("""
                    SELECT
                        market,
                        symbol,
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
                    AND timestamp >= ?
                    AND timestamp < ?
                    ORDER BY timestamp ASC
                """, (
                    symbol,
                    market,
                    timeframe,
                    start_utc,
                    end_utc,
                ))

                rows = cursor.fetchall()

            

        return [
            MarketData(
                market=row[0],
                symbol=row[1],
                timestamp=datetime.fromisoformat(row[2]),
                open=row[3],
                high=row[4],
                low=row[5],
                close=row[6],
                volume=row[7],
            )
            for row in rows
        ]
