
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from src.data_collection.market_data import MarketData
from src.data_collection.data_validator import validate_market_data


class MarketDataRepository:
    """
    Stores and retrieves market candles using SQLite.

    Candles are stored independently for each exchange.
    Existing records are migrated as Kraken data.
    """

    @staticmethod
    def default_path() -> Path:
        """database/market_data.db in the project folder."""
        return Path(__file__).resolve().parents[2] / "database" / "market_data.db"

    def __init__(self, db_path=None):

        if db_path is None:
            db_path = self.default_path()

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._initialize_database()

    @staticmethod
    def _validate_exchange(exchange: str) -> None:
        if not isinstance(exchange, str) or not exchange.strip():
            raise ValueError("Exchange must be a non-empty string.")

    def _initialize_database(self):

        with closing(sqlite3.connect(self.db_path)) as connection:
            with connection:
                cursor = connection.execute("""
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                    AND name = 'market_candles'
                """)

                table_exists = cursor.fetchone() is not None

                if not table_exists:
                    self._create_table(connection)
                    return

                columns = connection.execute("""
                    PRAGMA table_info(market_candles)
                """).fetchall()

                column_names = [column[1] for column in columns]

                if "exchange" in column_names:
                    return

                # Preserve the old table temporarily.
                connection.execute("""
                    ALTER TABLE market_candles
                    RENAME TO market_candles_legacy
                """)

                self._create_table(connection)

                # All existing records originated from Kraken.
                connection.execute("""
                    INSERT INTO market_candles (
                        exchange,
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
                    SELECT
                        'kraken',
                        market,
                        symbol,
                        timeframe,
                        timestamp,
                        open,
                        high,
                        low,
                        close,
                        volume
                    FROM market_candles_legacy
                """)

                connection.execute("""
                    DROP TABLE market_candles_legacy
                """)

    @staticmethod
    def _create_table(connection):

        connection.execute("""
            CREATE TABLE IF NOT EXISTS market_candles (
                exchange TEXT NOT NULL,
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
                    exchange,
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

            exchange = candle.exchange
            self._validate_exchange(exchange)

            timestamp = candle.timestamp.astimezone(
                timezone.utc
            ).isoformat()

            rows.append((
                exchange.lower().strip(),
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
                        exchange,
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
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

                    ON CONFLICT (
                        exchange,
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

    def get_latest_candle_timestamp(
        self,
        symbol: str,
        market: str,
        timeframe: str,
        exchange: str = "kraken",
    ) -> datetime | None:

        self._validate_exchange(exchange)

        with closing(sqlite3.connect(self.db_path)) as connection:
            cursor = connection.execute("""
                SELECT MAX(timestamp)
                FROM market_candles
                WHERE exchange = ?
                AND symbol = ?
                AND market = ?
                AND timeframe = ?
            """, (
                exchange.lower().strip(),
                symbol,
                market,
                timeframe,
            ))

            row = cursor.fetchone()

        if row[0] is None:
            return None

        return datetime.fromisoformat(row[0])

    def get_earliest_candle_timestamp(
        self,
        symbol: str,
        market: str,
        timeframe: str,
        exchange: str = "kraken",
    ) -> datetime | None:

        self._validate_exchange(exchange)

        with closing(sqlite3.connect(self.db_path)) as connection:
            cursor = connection.execute("""
                SELECT MIN(timestamp)
                FROM market_candles
                WHERE exchange = ?
                AND symbol = ?
                AND market = ?
                AND timeframe = ?
            """, (
                exchange.lower().strip(),
                symbol,
                market,
                timeframe,
            ))

            row = cursor.fetchone()

        if row[0] is None:
            return None

        return datetime.fromisoformat(row[0])

    def get_candle_timestamps(
        self,
        symbol: str,
        market: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        exchange: str = "kraken",
    ) -> list[datetime]:

        self._validate_exchange(exchange)

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
            cursor = connection.execute("""
                SELECT timestamp
                FROM market_candles
                WHERE exchange = ?
                AND symbol = ?
                AND market = ?
                AND timeframe = ?
                AND timestamp >= ?
                AND timestamp < ?
                ORDER BY timestamp ASC
            """, (
                exchange.lower().strip(),
                symbol,
                market,
                timeframe,
                start_utc,
                end_utc,
            ))

            rows = cursor.fetchall()

        return [
            datetime.fromisoformat(row[0])
            for row in rows
        ]

    def get_candles(
        self,
        symbol: str,
        market: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        exchange: str = "kraken",
    ) -> list[MarketData]:

        self._validate_exchange(exchange)

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
            cursor = connection.execute("""
                SELECT
                    exchange,
                    market,
                    symbol,
                    timestamp,
                    open,
                    high,
                    low,
                    close,
                    volume
                FROM market_candles
                WHERE exchange = ?
                AND symbol = ?
                AND market = ?
                AND timeframe = ?
                AND timestamp >= ?
                AND timestamp < ?
                ORDER BY timestamp ASC
            """, (
                exchange.lower().strip(),
                symbol,
                market,
                timeframe,
                start_utc,
                end_utc,
            ))

            rows = cursor.fetchall()

        return [
            MarketData(
                exchange=row[0],
                market=row[1],
                symbol=row[2],
                timestamp=datetime.fromisoformat(row[3]),
                open=row[4],
                high=row[5],
                low=row[6],
                close=row[7],
                volume=row[8],
            )
            for row in rows
        ]
