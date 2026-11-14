
import csv
from datetime import datetime, timezone
from pathlib import Path

from src.data_collection.market_data import MarketData
from src.data_collection.data_validator import validate_market_data
from src.data_collection.market_data_repository import MarketDataRepository


class HistoricalDataImporter:
    """
    Imports Kraken historical OHLCVT CSV data into SQLite.
    """

    SYMBOL = "BTC/USD"
    MARKET = "crypto"
    TIMEFRAME = "1h"
    BATCH_SIZE = 10_000

    def __init__(
        self,
        repository: MarketDataRepository,
        batch_size: int = BATCH_SIZE,
    ):
        if batch_size < 1:
            raise ValueError("Batch size must be greater than zero.")

        self.repository = repository
        self.batch_size = batch_size

    def import_kraken_csv(self, csv_path: str | Path) -> dict:
        """
        Import a Kraken BTC/USD hourly OHLCVT CSV file.

        Expected columns:
        timestamp, open, high, low, close, volume, trades

        The CSV has no header row.
        """

        csv_path = Path(csv_path)

        if not csv_path.is_file():
            raise FileNotFoundError(
                f"Historical CSV file not found: {csv_path}"
            )

        batch = []
        imported = 0
        line_number = 0

        def save_batch():
            nonlocal imported

            if not batch:
                return

            imported += self.repository.save_candles(
                candles=batch,
                timeframe=self.TIMEFRAME,
            )

            batch.clear()

        with csv_path.open(
            "r",
            newline="",
            encoding="utf-8",
        ) as file:

            reader = csv.reader(file)

            for line_number, row in enumerate(reader, start=1):

                if not row:
                    continue

                if len(row) != 7:
                    raise ValueError(
                        f"Invalid column count on CSV line {line_number}. "
                        f"Expected 7, received {len(row)}."
                    )

                try:
                    timestamp = datetime.fromtimestamp(
                        float(row[0]),
                        tz=timezone.utc,
                    )

                    candle = MarketData(
                        symbol=self.SYMBOL,
                        market=self.MARKET,
                        timestamp=timestamp,
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=float(row[5]),
                    )

                except (ValueError, OverflowError, OSError) as exc:
                    raise ValueError(
                        f"Could not parse CSV line {line_number}: {exc}"
                    ) from exc

                errors = validate_market_data(candle)

                if errors:
                    raise ValueError(
                        f"Invalid candle on CSV line {line_number}: "
                        f"{'; '.join(errors)}"
                    )

                if (
                    timestamp.minute != 0
                    or timestamp.second != 0
                    or timestamp.microsecond != 0
                ):
                    raise ValueError(
                        f"Unexpected hourly timestamp on CSV line "
                        f"{line_number}: {timestamp}"
                    )

                batch.append(candle)

                if len(batch) >= self.batch_size:
                    save_batch()

        save_batch()

        return {
            "file": str(csv_path),
            "symbol": self.SYMBOL,
            "timeframe": self.TIMEFRAME,
            "rows_read": line_number,
            "rows_processed": imported,
        }
