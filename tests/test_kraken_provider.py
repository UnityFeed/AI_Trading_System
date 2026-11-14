
import json
import unittest
from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import patch

from src.data_collection.kraken_provider import KrakenProvider


class TestKrakenProvider(unittest.TestCase):

    def setUp(self):
        self.provider = KrakenProvider()

        self.start = datetime(
            2026, 11, 13, 11, 0, tzinfo=timezone.utc
        )

        self.end = datetime(
            2026, 11, 13, 14, 0, tzinfo=timezone.utc
        )

    @patch("src.data_collection.kraken_provider.urlopen")
    def test_fetch_candles(self, mock_urlopen):

        sample_response = {
            "error": [],
            "result": {
                "XXBTZUSD": [
                    [
                        1794567600,
                        "95000.0",
                        "96000.0",
                        "94000.0",
                        "95500.0",
                        "95000.0",
                        "125.5",
                        100
                    ],
                    [
                        1794571200,
                        "95500.0",
                        "97000.0",
                        "95000.0",
                        "96500.0",
                        "96000.0",
                        "150.5",
                        120
                    ],
                    [
                        1794574800,
                        "96500.0",
                        "98000.0",
                        "96000.0",
                        "97500.0",
                        "97000.0",
                        "175.5",
                        140
                    ],
                ],
                "last": 1794574800
            }
        }

        mock_urlopen.return_value = BytesIO(
            json.dumps(sample_response).encode("utf-8")
        )

        candles = self.provider.fetch_candles(
            "BTC/USD",
            "1h",
            self.start,
            self.end,
        )

        self.assertEqual(len(candles), 2)
        self.assertEqual(candles[0].symbol, "BTC/USD")
        self.assertEqual(candles[0].market, "crypto")
        self.assertEqual(candles[0].close, 95500.0)
        self.assertEqual(candles[1].close, 96500.0)

        self.assertEqual(
            candles[0].timestamp.tzinfo,
            timezone.utc
        )


    @patch("src.data_collection.kraken_provider.urlopen")
    def test_only_unfinished_candle_returns_empty_list(self, mock_urlopen):

        unfinished_timestamp = int(
            self.start.timestamp()
        )

        sample_response = {
            "error": [],
            "result": {
                "XXBTZUSD": [
                    [
                        unfinished_timestamp,
                        "95000.0",
                        "96000.0",
                        "94000.0",
                        "95500.0",
                        "95000.0",
                        "125.5",
                        100
                    ],
                ],
                "last": unfinished_timestamp
            }
        }

        mock_urlopen.return_value = BytesIO(
            json.dumps(sample_response).encode("utf-8")
        )

        candles = self.provider.fetch_candles(
            "BTC/USD",
            "1h",
            self.start,
            self.end,
        )

        self.assertEqual(candles, [])

    @patch("src.data_collection.kraken_provider.urlopen")
    def test_historical_candles_are_kept(self, mock_urlopen):

        current_timestamp = int(
            datetime(2026, 11, 14, 13, 0, tzinfo=timezone.utc).timestamp()
        )

        sample_response = {
            "error": [],
            "result": {
                "XXBTZUSD": [
                    [
                        1794567600,
                        "95000.0",
                        "96000.0",
                        "94000.0",
                        "95500.0",
                        "95000.0",
                        "125.5",
                        100
                    ],
                    [
                        1794571200,
                        "95500.0",
                        "97000.0",
                        "95000.0",
                        "96500.0",
                        "96000.0",
                        "150.5",
                        120
                    ],
                    [
                        current_timestamp,
                        "96500.0",
                        "98000.0",
                        "96000.0",
                        "97500.0",
                        "97000.0",
                        "175.5",
                        140
                    ],
                ],
                "last": current_timestamp
            }
        }

        mock_urlopen.return_value = BytesIO(
            json.dumps(sample_response).encode("utf-8")
        )

        candles = self.provider.fetch_candles(
            "BTC/USD",
            "1h",
            self.start,
            self.end,
        )

        self.assertEqual(len(candles), 2)
        self.assertEqual(candles[0].close, 95500.0)
        self.assertEqual(candles[1].close, 96500.0)


    def test_unsupported_symbol_is_rejected(self):
        with self.assertRaises(ValueError):
            self.provider.fetch_candles(
                "DOGE/USD",
                "1h",
                self.start,
                self.end,
            )

    def test_unsupported_timeframe_is_rejected(self):
        with self.assertRaises(ValueError):
            self.provider.fetch_candles(
                "BTC/USD",
                "2h",
                self.start,
                self.end,
            )


if __name__ == "__main__":
    unittest.main()
