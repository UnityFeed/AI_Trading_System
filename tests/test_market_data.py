
import unittest
from datetime import datetime, timezone

from src.data_collection.market_data import MarketData


class TestMarketData(unittest.TestCase):

    def test_create_market_data(self):
        candle = MarketData(
            symbol="BTC/USD",
            market="crypto",
            timestamp=datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc),
            open=95000.0,
            high=96000.0,
            low=94000.0,
            close=95500.0,
            volume=125.5
        )

        self.assertEqual(candle.symbol, "BTC/USD")
        self.assertEqual(candle.market, "crypto")
        self.assertEqual(candle.close, 95500.0)
        self.assertEqual(candle.volume, 125.5)


if __name__ == "__main__":
    unittest.main()
