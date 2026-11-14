
import sqlite3
from pathlib import Path

from src.data_collection.market_data_repository import MarketDataRepository
from src.data_collection.historical_data_importer import HistoricalDataImporter


def main():

    project_root = Path(__file__).resolve().parents[1]

    csv_path = (
        project_root
        / "data"
        / "historical"
        / "extracted"
        / "XBTUSD_60.csv"
    )

    repository = MarketDataRepository()

    importer = HistoricalDataImporter(
        repository=repository,
    )

    print("Starting BTC/USD historical data import...")
    print(f"Exchange: {importer.EXCHANGE}")
    print(f"Source: {csv_path}")
    print(f"Database: {repository.db_path}")

    result = importer.import_kraken_csv(csv_path)

    print("\nIMPORT COMPLETE")
    print("----------------")
    print(f"Exchange: {result['exchange']}")
    print(f"Rows processed: {result['rows_processed']:,}")
    print(f"Symbol: {result['symbol']}")
    print(f"Timeframe: {result['timeframe']}")

    with sqlite3.connect(repository.db_path) as connection:

        row = connection.execute("""
            SELECT
                COUNT(*),
                MIN(timestamp),
                MAX(timestamp)
            FROM market_candles
            WHERE exchange = ?
            AND symbol = ?
            AND market = ?
            AND timeframe = ?
        """, (
            importer.EXCHANGE,
            importer.SYMBOL,
            importer.MARKET,
            importer.TIMEFRAME,
        )).fetchone()

    print("\nDATABASE REPORT")
    print("----------------")
    print(f"Exchange: {importer.EXCHANGE}")
    print(f"Total BTC/USD hourly candles: {row[0]:,}")
    print(f"Earliest candle: {row[1]}")
    print(f"Latest candle: {row[2]}")


if __name__ == "__main__":
    main()
