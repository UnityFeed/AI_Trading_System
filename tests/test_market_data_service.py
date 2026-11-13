
import unittest
from datetime import datetime, timezone

from src.data_collection.market_data import MarketData
from src.data_collection.market_data_provider import MarketDataProvider
from src.data_collection.market_data_service import MarketDataService


class ExampleProvider(MarketDataProvider):

    def __init__(self, candles=None):
        self.candles = candles

    def fetch_candles(self, symbol, timeframe, start, end):

        if self.candles is not None:
            return self.candles

        return [
            MarketData(
                symbol="BTC/USD",
                market="crypto",
                timestamp=datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc),
                open=95000.0,
                high=96000.0,
                low=94000.0,
                close=95500.0,
                volume=125.5,
            )
        ]


class TestMarketDataService(unittest.TestCase):

    def setUp(self):
        self.start = datetime(2026, 11, 13, 11, 0, tzinfo=timezone.utc)
        self.end = datetime(2026, 11, 13, 13, 0, tzinfo=timezone.utc)
        self.service = MarketDataService(ExampleProvider())

    def create_candle(self, hour):
        return MarketData(
            symbol="BTC/USD",
            market="crypto",
            timestamp=datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc),
            open=95000.0,
            high=96000.0,
            low=94000.0,
            close=95500.0,
            volume=125.5,
        )

    def test_valid_candles_are_returned(self):
        candles = self.service.get_candles(
            "BTC/USD", "1h", self.start, self.end
        )

        self.assertEqual(len(candles), 1)
        self.assertEqual(candles[0].symbol, "BTC/USD")

    def test_invalid_time_range_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.get_candles(
                "BTC/USD", "1h", self.end, self.start
            )

    def test_wrong_symbol_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.get_candles(
                "ETH/USD", "1h", self.start, self.end
            )

    def test_timestamp_outside_range_is_rejected(self):
        outside_candle = MarketData(
            symbol="BTC/USD",
            market="crypto",
            timestamp=datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc),
            open=95000.0,
            high=96000.0,
            low=94000.0,
            close=95500.0,
            volume=125.5,
        )

        provider = ExampleProvider([outside_candle])
        service = MarketDataService(provider)

        with self.assertRaises(ValueError):
            service.get_candles(
                "BTC/USD", "1h", self.start, self.end
            )

    def test_duplicate_timestamps_are_rejected(self):
        provider = ExampleProvider([
            self.create_candle(12),
            self.create_candle(12),
        ])
        service = MarketDataService(provider)

        with self.assertRaises(ValueError):
            service.get_candles(
                "BTC/USD", "1h", self.start, self.end
            )

    def test_out_of_order_candles_are_rejected(self):
        provider = ExampleProvider([
            self.create_candle(12),
            self.create_candle(11),
        ])
        service = MarketDataService(provider)

        with self.assertRaises(ValueError):
            service.get_candles(
                "BTC/USD", "1h", self.start, self.end
            )


if __name__ == "__main__":
    unittest.main()
