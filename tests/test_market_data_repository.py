
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


    def test_get_latest_candle_timestamp(self):

        second_candle = MarketData(
            symbol="BTC/USD",
            market="crypto",
            timestamp=self.timestamp + timedelta(hours=1),
            open=95500.0,
            high=97000.0,
            low=95000.0,
            close=96500.0,
            volume=150.0,
        )

        third_candle = MarketData(
            symbol="BTC/USD",
            market="crypto",
            timestamp=self.timestamp + timedelta(hours=2),
            open=96500.0,
            high=98000.0,
            low=96000.0,
            close=97500.0,
            volume=175.0,
        )

        self.repository.save_candles(
            [self.candle, second_candle, third_candle],
            "1h",
        )

        latest = self.repository.get_latest_candle_timestamp(
            "BTC/USD",
            "crypto",
            "1h",
        )

        self.assertEqual(
            latest,
            self.timestamp + timedelta(hours=2),
        )

    def test_latest_candle_timestamp_returns_none_when_empty(self):

        latest = self.repository.get_latest_candle_timestamp(
            "BTC/USD",
            "crypto",
            "1h",
        )

        self.assertIsNone(latest)

    def test_latest_timestamp_is_separated_by_timeframe(self):

        self.repository.save_candles(
            [self.candle],
            "1h",
        )

        latest_1h = self.repository.get_latest_candle_timestamp(
            "BTC/USD",
            "crypto",
            "1h",
        )

        latest_4h = self.repository.get_latest_candle_timestamp(
            "BTC/USD",
            "crypto",
            "4h",
        )

        self.assertEqual(latest_1h, self.timestamp)
        self.assertIsNone(latest_4h)


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

    def test_get_candle_timestamps(self):

        second_candle = MarketData(
            symbol="BTC/USD",
            market="crypto",
            timestamp=self.timestamp + timedelta(hours=1),
            open=95500.0,
            high=97000.0,
            low=95000.0,
            close=96500.0,
            volume=150.0,
        )

        self.repository.save_candles(
            [self.candle, second_candle],
            "1h",
        )

        timestamps = self.repository.get_candle_timestamps(
            "BTC/USD",
            "crypto",
            "1h",
            self.timestamp,
            self.timestamp + timedelta(hours=2),
        )

        self.assertEqual(
            timestamps,
            [
                self.timestamp,
                self.timestamp + timedelta(hours=1),
            ],
        )

    def test_get_candle_timestamps_returns_empty_list(self):

        timestamps = self.repository.get_candle_timestamps(
            "BTC/USD",
            "crypto",
            "1h",
            self.timestamp,
            self.timestamp + timedelta(hours=2),
        )

        self.assertEqual(timestamps, [])

    def test_get_candle_timestamps_rejects_invalid_range(self):

        with self.assertRaises(ValueError):
            self.repository.get_candle_timestamps(
                "BTC/USD",
                "crypto",
                "1h",
                self.timestamp + timedelta(hours=2),
                self.timestamp,
            )

    def test_get_earliest_candle_timestamp(self):

        second_candle = MarketData(
            symbol="BTC/USD",
            market="crypto",
            timestamp=self.timestamp + timedelta(hours=1),
            open=95500.0,
            high=97000.0,
            low=95000.0,
            close=96500.0,
            volume=150.0,
        )

        self.repository.save_candles(
            [second_candle, self.candle],
            "1h",
        )

        earliest = self.repository.get_earliest_candle_timestamp(
            "BTC/USD",
            "crypto",
            "1h",
        )

        self.assertEqual(earliest, self.timestamp)

    def test_earliest_candle_timestamp_returns_none_when_empty(self):

        earliest = self.repository.get_earliest_candle_timestamp(
            "BTC/USD",
            "crypto",
            "1h",
        )

        self.assertIsNone(earliest)

if __name__ == "__main__":
    unittest.main()
