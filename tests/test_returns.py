import unittest
from dataclasses import replace
from datetime import datetime, timedelta

from src.analysis.returns import calculate_hourly_returns
from tests.helpers import BASE_TIME, hourly_candles


class TestCalculateHourlyReturns(unittest.TestCase):

    def test_close_to_close_returns_in_percent(self):

        candles = hourly_candles([100, 110, 99])

        returns = calculate_hourly_returns(candles)

        self.assertEqual(len(returns), 2)
        self.assertAlmostEqual(returns[0].return_pct, 10.0)
        self.assertAlmostEqual(returns[1].return_pct, -10.0)

        first = returns[0]
        self.assertEqual(first.previous_timestamp, BASE_TIME)
        self.assertEqual(first.timestamp, BASE_TIME + timedelta(hours=1))
        self.assertEqual(first.previous_close, 100)
        self.assertEqual(first.close, 110)
        self.assertEqual(first.exchange, "kraken")
        self.assertEqual(first.symbol, "BTC/USD")

    def test_no_return_is_calculated_across_a_missing_hour(self):

        # Hour 2 is missing, so there is no 1 -> 3 return.
        candles = hourly_candles(
            [100, 110, 999, 121, 133.1],
            skip_hours={2},
        )

        returns = calculate_hourly_returns(candles)

        self.assertEqual(
            [r.timestamp for r in returns],
            [BASE_TIME + timedelta(hours=1), BASE_TIME + timedelta(hours=4)],
        )
        self.assertAlmostEqual(returns[0].return_pct, 10.0)
        self.assertAlmostEqual(returns[1].return_pct, 10.0)

    def test_unsorted_input_is_sorted_by_time(self):

        candles = hourly_candles([100, 110, 121])

        returns = calculate_hourly_returns(list(reversed(candles)))

        self.assertEqual(len(returns), 2)
        self.assertTrue(all(abs(r.return_pct - 10.0) < 1e-9 for r in returns))

    def test_single_candle_and_empty_input_give_no_returns(self):

        self.assertEqual(calculate_hourly_returns([]), [])
        self.assertEqual(calculate_hourly_returns(hourly_candles([100])), [])

    def test_mixed_exchanges_are_rejected(self):

        candles = hourly_candles([100])
        candles += hourly_candles(
            [110], start=BASE_TIME + timedelta(hours=1), exchange="bitstamp"
        )

        with self.assertRaises(ValueError):
            calculate_hourly_returns(candles)

    def test_mixed_symbols_are_rejected(self):

        candles = hourly_candles([100])
        candles += hourly_candles(
            [110], start=BASE_TIME + timedelta(hours=1), symbol="ETH/USD"
        )

        with self.assertRaises(ValueError):
            calculate_hourly_returns(candles)

    def test_naive_timestamps_are_rejected(self):

        candles = [
            replace(hourly_candles([100])[0], timestamp=datetime(2026, 11, 14))
        ]

        with self.assertRaises(ValueError):
            calculate_hourly_returns(candles)

    def test_zero_previous_close_is_rejected(self):

        candles = hourly_candles([0, 110])

        with self.assertRaises(ValueError):
            calculate_hourly_returns(candles)


if __name__ == "__main__":
    unittest.main()
