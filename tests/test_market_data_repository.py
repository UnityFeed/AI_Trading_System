
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.data_collection.market_data import MarketData
from src.data_collection.market_data_repository import MarketDataRepository


class TestMarketDataRepository(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

        db_path = Path(self.temp_dir.name) / "test_market_data.db"

        self.repository = MarketDataRepository(db_path)

        self.timestamp = datetime(
            2026, 11, 13, 12, 0, tzinfo=timezone.utc
        )

        self.candle = MarketData(
            symbol="BTC/USD",
            market="crypto",
            timestamp=self.timestamp,
            open=95000.0,
            high=96000.0,
            low=94000.0,
            close=95500.0,
            volume=125.5,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_and_retrieve_candle(self):

        saved = self.repository.save_candles(
            [self.candle],
            "1h",
        )

        retrieved = self.repository.get_candles(
            symbol="BTC/USD",
            market="crypto",
            timeframe="1h",
            start=self.timestamp - timedelta(hours=1),
            end=self.timestamp + timedelta(hours=1),
        )

        self.assertEqual(saved, 1)
        self.assertEqual(len(retrieved), 1)
        self.assertEqual(retrieved[0].symbol, "BTC/USD")
        self.assertEqual(retrieved[0].close, 95500.0)
        self.assertEqual(retrieved[0].volume, 125.5)
        self.assertEqual(retrieved[0].timestamp, self.timestamp)

    def test_duplicate_candle_is_updated(self):

        self.repository.save_candles(
            [self.candle],
            "1h",
        )

        updated_candle = MarketData(
            symbol="BTC/USD",
            market="crypto",
            timestamp=self.timestamp,
            open=95000.0,
            high=97000.0,
            low=94000.0,
            close=96500.0,
            volume=150.0,
        )

        self.repository.save_candles(
            [updated_candle],
            "1h",
        )

        retrieved = self.repository.get_candles(
            "BTC/USD",
            "crypto",
            "1h",
            self.timestamp - timedelta(hours=1),
            self.timestamp + timedelta(hours=1),
        )

        self.assertEqual(len(retrieved), 1)
        self.assertEqual(retrieved[0].close, 96500.0)
        self.assertEqual(retrieved[0].volume, 150.0)

    def test_invalid_candle_is_rejected(self):

        invalid_candle = MarketData(
            symbol="BTC/USD",
            market="crypto",
            timestamp=self.timestamp,
            open=95000.0,
            high=94000.0,
            low=93000.0,
            close=95500.0,
            volume=125.5,
        )

        with self.assertRaises(ValueError):
            self.repository.save_candles(
                [invalid_candle],
                "1h",
            )

    def test_empty_timeframe_is_rejected(self):

        with self.assertRaises(ValueError):
            self.repository.save_candles(
                [self.candle],
                "",
            )

    def test_naive_timestamp_range_is_rejected(self):

        naive_start = datetime(2026, 11, 13, 11, 0)

        with self.assertRaises(ValueError):
            self.repository.get_candles(
                "BTC/USD",
                "crypto",
                "1h",
                naive_start,
                self.timestamp + timedelta(hours=1),
            )

    def test_invalid_time_range_is_rejected(self):

        with self.assertRaises(ValueError):
            self.repository.get_candles(
                "BTC/USD",
                "crypto",
                "1h",
                self.timestamp + timedelta(hours=1),
                self.timestamp,
            )


if __name__ == "__main__":
    unittest.main()
