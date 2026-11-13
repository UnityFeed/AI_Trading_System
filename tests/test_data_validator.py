
import unittest
from datetime import datetime, timezone

from src.data_collection.market_data import MarketData
from src.data_collection.data_validator import validate_market_data


class TestDataValidator(unittest.TestCase):

    def setUp(self):
        self.valid_candle = MarketData(
            symbol="BTC/USD",
            market="crypto",
            timestamp=datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc),
            open=95000.0,
            high=96000.0,
            low=94000.0,
            close=95500.0,
            volume=125.5
        )

    def test_valid_candle(self):
        errors = validate_market_data(self.valid_candle)
        self.assertEqual(errors, [])

    def test_invalid_high_price(self):
        self.valid_candle.high = 93000.0

        errors = validate_market_data(self.valid_candle)

        self.assertIn(
            "High cannot be lower than another candle price.",
            errors
        )

    def test_negative_volume(self):
        self.valid_candle.volume = -10.0

        errors = validate_market_data(self.valid_candle)

        self.assertIn(
            "Volume must be a finite, non-negative number.",
            errors
        )

    def test_zero_price(self):
        self.valid_candle.close = 0

        errors = validate_market_data(self.valid_candle)

        self.assertIn(
            "close must be greater than zero.",
            errors
        )

    def test_invalid_market(self):
        self.valid_candle.market = "unknown"

        errors = validate_market_data(self.valid_candle)

        self.assertIn(
            "Market must be stock, crypto, or forex.",
            errors
        )

    def test_timezone_naive_timestamp_is_rejected(self):
        self.valid_candle.timestamp = datetime(2026, 11, 13, 12, 0)

        errors = validate_market_data(self.valid_candle)

        self.assertIn(
            "Timestamp must be a timezone-aware datetime value.",
         errors
        )

if __name__ == "__main__":
    unittest.main()
