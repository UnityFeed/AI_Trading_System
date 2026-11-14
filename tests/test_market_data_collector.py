import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock

from src.data_collection.market_data import MarketData
from src.data_collection.market_data_collector import MarketDataCollector


class TestMarketDataCollector(unittest.TestCase):

    def setUp(self):

        self.service = Mock()
        self.repository = Mock()

        self.collector = MarketDataCollector(
            market_data_service=self.service,
            repository=self.repository,
        )

        self.start = datetime(
            2026, 11, 14, 10, 0, tzinfo=timezone.utc
        )

        self.end = datetime(
            2026, 11, 14, 14, 0, tzinfo=timezone.utc
        )

        self.repository.get_earliest_candle_timestamp.return_value = None
        self.repository.get_candle_timestamps.return_value = []
        self.repository.save_candles.return_value = 0
        self.service.get_candles.return_value = []

    def test_collection_uses_initial_start_when_database_is_empty(self):

        result = self.collector.collect(
            end=self.end,
            initial_start=self.start,
        )

        self.assertEqual(result["start"], self.start)
        self.assertEqual(result["fetched"], 0)
        self.assertEqual(result["saved"], 0)
        self.assertEqual(result["missing_remaining"], 4)

        self.service.get_candles.assert_called_once()

    def test_initial_start_is_required_when_database_is_empty(self):

        with self.assertRaises(ValueError):
            self.collector.collect(end=self.end)

        self.service.get_candles.assert_not_called()

    def test_existing_candles_are_not_fetched_again(self):

        expected_timestamps = [
            self.start + timedelta(hours=i)
            for i in range(4)
        ]

        self.repository.get_earliest_candle_timestamp.return_value = self.start
        self.repository.get_candle_timestamps.return_value = expected_timestamps

        result = self.collector.collect(end=self.end)

        self.assertEqual(result["fetched"], 0)
        self.assertEqual(result["saved"], 0)
        self.assertEqual(result["missing_remaining"], 0)

        self.service.get_candles.assert_not_called()
        self.repository.save_candles.assert_not_called()

    def test_missing_candles_are_fetched_and_saved(self):

        existing = [
            self.start,
            self.start + timedelta(hours=2),
        ]

        missing_candles = [
            MarketData(
                symbol="BTC/USD",
                market="crypto",
                timestamp=self.start + timedelta(hours=1),
                open=95000.0,
                high=96000.0,
                low=94000.0,
                close=95500.0,
                volume=100.0,
            ),
            MarketData(
                symbol="BTC/USD",
                market="crypto",
                timestamp=self.start + timedelta(hours=3),
                open=95500.0,
                high=97000.0,
                low=95000.0,
                close=96500.0,
                volume=120.0,
            ),
        ]

        self.repository.get_earliest_candle_timestamp.return_value = self.start

        self.repository.get_candle_timestamps.side_effect = [
            existing,
            existing + [
                self.start + timedelta(hours=1),
                self.start + timedelta(hours=3),
            ],
        ]

        self.service.get_candles.return_value = missing_candles
        self.repository.save_candles.return_value = 2

        result = self.collector.collect(end=self.end)

        self.assertEqual(result["fetched"], 2)
        self.assertEqual(result["saved"], 2)
        self.assertEqual(result["missing_remaining"], 0)

        self.repository.save_candles.assert_called_once_with(
            candles=missing_candles,
            timeframe="1h",
        )

    def test_end_time_is_rounded_down_to_full_hour(self):

        end_with_minutes = self.end + timedelta(minutes=35)

        result = self.collector.collect(
            end=end_with_minutes,
            initial_start=self.start,
        )

        self.assertEqual(result["end"], self.end)

    def test_naive_end_time_is_rejected(self):

        naive_end = datetime(2026, 11, 14, 14, 0)

        with self.assertRaises(ValueError):
            self.collector.collect(end=naive_end)


if __name__ == "__main__":
    unittest.main()