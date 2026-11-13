
import unittest
from datetime import datetime, timezone

from src.data_collection.market_data import MarketData
from src.data_collection.market_data_provider import MarketDataProvider


class ExampleProvider(MarketDataProvider):

    def fetch_candles(self, symbol, timeframe, start, end):
        return [
            MarketData(
                symbol=symbol,
                market="crypto",
                timestamp=datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc),
                open=95000.0,
                high=96000.0,
                low=94000.0,
                close=95500.0,
                volume=125.5,
            )
        ]


class TestMarketDataProvider(unittest.TestCase):

    def test_provider_returns_market_data(self):
        provider = ExampleProvider()

        candles = provider.fetch_candles(
            symbol="BTC/USD",
            timeframe="1h",
            start=datetime(2026, 11, 13, 11, 0, tzinfo=timezone.utc),
            end=datetime(2026, 11, 13, 13, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(len(candles), 1)
        self.assertIsInstance(candles[0], MarketData)
        self.assertEqual(candles[0].symbol, "BTC/USD")

    def test_base_provider_cannot_be_instantiated(self):
        with self.assertRaises(TypeError):
            MarketDataProvider()


if __name__ == "__main__":
    unittest.main()
