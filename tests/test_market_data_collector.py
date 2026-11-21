import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock

from src.data_collection.market_data import MarketData
from src.data_collection.market_data_collector import MarketDataCollector


def make_candle(timestamp: datetime) -> MarketData:
    return MarketData(
        symbol="BTC/USD",
        market="crypto",
        timestamp=timestamp,
        open=95000.0,
        high=96000.0,
        low=94000.0,
        close=95500.0,
        volume=100.0,
        exchange="kraken",
    )


class TestMarketDataCollector(unittest.TestCase):
    """
    The collector only collects forward: it continues one hour after the
    latest stored Kraken candle and stops at the last completed hour.
    """

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

        # Default: the database holds no Kraken candles yet.
        self.repository.get_latest_candle_timestamp.return_value = None
        self.repository.save_candles.return_value = 0
        self.service.get_candles.return_value = []

    def test_latest_candle_is_looked_up_for_kraken_explicitly(self):

        self.collector.collect(end=self.end, initial_start=self.start)

        self.repository.get_latest_candle_timestamp.assert_called_once_with(
            symbol="BTC/USD",
            market="crypto",
            timeframe="1h",
            exchange="kraken",
        )

    def test_collection_uses_initial_start_when_database_is_empty(self):

        result = self.collector.collect(
            end=self.end,
            initial_start=self.start,
        )

        self.assertEqual(result["start"], self.start)
        self.assertEqual(result["end"], self.end)
        self.assertEqual(result["fetched"], 0)
        self.assertEqual(result["saved"], 0)
        # 10:00, 11:00, 12:00 and 13:00 were expected but not returned.
        self.assertEqual(result["unreturned_hours"], 4)

        self.service.get_candles.assert_called_once_with(
            symbol="BTC/USD",
            timeframe="1h",
            start=self.start,
            end=self.end,
        )

    def test_initial_start_is_required_when_database_is_empty(self):

        with self.assertRaises(ValueError):
            self.collector.collect(end=self.end)

        self.service.get_candles.assert_not_called()

    def test_initial_start_must_be_aligned_to_full_hour(self):

        with self.assertRaises(ValueError):
            self.collector.collect(
                end=self.end,
                initial_start=self.start + timedelta(minutes=15),
            )

        self.service.get_candles.assert_not_called()

    def test_nothing_is_fetched_when_database_is_up_to_date(self):

        # The 13:00 candle covers 13:00-14:00, the last completed hour.
        self.repository.get_latest_candle_timestamp.return_value = (
            self.end - timedelta(hours=1)
        )

        result = self.collector.collect(end=self.end)

        self.assertEqual(result["start"], self.end)
        self.assertEqual(result["fetched"], 0)
        self.assertEqual(result["saved"], 0)
        self.assertEqual(result["unreturned_hours"], 0)

        self.service.get_candles.assert_not_called()
        self.repository.save_candles.assert_not_called()

    def test_collection_continues_one_hour_after_latest_candle(self):

        # 10:00 and 11:00 are stored; 12:00 and 13:00 are new.
        latest = self.start + timedelta(hours=1)
        self.repository.get_latest_candle_timestamp.return_value = latest

        new_candles = [
            make_candle(self.start + timedelta(hours=2)),
            make_candle(self.start + timedelta(hours=3)),
        ]

        self.service.get_candles.return_value = new_candles
        self.repository.save_candles.return_value = 2

        result = self.collector.collect(end=self.end)

        expected_start = self.start + timedelta(hours=2)

        self.assertEqual(result["start"], expected_start)
        self.assertEqual(result["fetched"], 2)
        self.assertEqual(result["saved"], 2)
        self.assertEqual(result["unreturned_hours"], 0)

        self.service.get_candles.assert_called_once_with(
            symbol="BTC/USD",
            timeframe="1h",
            start=expected_start,
            end=self.end,
        )
        self.repository.save_candles.assert_called_once_with(
            candles=new_candles,
            timeframe="1h",
        )

    def test_hours_the_exchange_did_not_return_are_reported(self):

        self.repository.get_latest_candle_timestamp.return_value = (
            self.start + timedelta(hours=1)
        )

        # Kraken returns 13:00 but not 12:00. The gap is preserved,
        # not filled with a made-up candle.
        self.service.get_candles.return_value = [
            make_candle(self.start + timedelta(hours=3)),
        ]
        self.repository.save_candles.return_value = 1

        result = self.collector.collect(end=self.end)

        self.assertEqual(result["fetched"], 1)
        self.assertEqual(result["saved"], 1)
        self.assertEqual(result["unreturned_hours"], 1)

    def test_large_gaps_are_refused(self):

        latest = self.end - timedelta(
            hours=MarketDataCollector.MAX_FETCH_HOURS + 2
        )
        self.repository.get_latest_candle_timestamp.return_value = latest

        with self.assertRaises(RuntimeError):
            self.collector.collect(end=self.end)

        self.service.get_candles.assert_not_called()

    def test_end_time_is_rounded_down_to_full_hour(self):

        end_with_minutes = self.end + timedelta(minutes=35)

        result = self.collector.collect(
            end=end_with_minutes,
            initial_start=self.start,
        )

        self.assertEqual(result["end"], self.end)

    def test_non_utc_end_time_is_converted_to_utc(self):

        amsterdam_winter = timezone(timedelta(hours=1))
        local_end = datetime(2026, 11, 14, 15, 0, tzinfo=amsterdam_winter)

        result = self.collector.collect(
            end=local_end,
            initial_start=self.start,
        )

        self.assertEqual(result["end"], self.end)
        self.assertEqual(result["end"].tzinfo, timezone.utc)

    def test_naive_end_time_is_rejected(self):

        naive_end = datetime(2026, 11, 14, 14, 0)

        with self.assertRaises(ValueError):
            self.collector.collect(end=naive_end)


if __name__ == "__main__":
    unittest.main()
