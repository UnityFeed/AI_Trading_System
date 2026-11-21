import unittest
from dataclasses import replace
from datetime import datetime, timedelta

from src.analysis.indicators import calculate_hourly_sma
from tests.helpers import BASE_TIME, hourly_candles


class TestCalculateHourlySma(unittest.TestCase):

    def test_first_average_appears_once_window_is_full(self):

        candles = hourly_candles([10, 20, 30, 40, 50])

        averages = calculate_hourly_sma(candles, period_hours=3)

        # Windows: (10,20,30) (20,30,40) (30,40,50)
        self.assertEqual([a.value for a in averages], [20.0, 30.0, 40.0])

        # Each average is stamped with the last candle in its window,
        # so it only uses candles up to and including that hour.
        self.assertEqual(
            [a.timestamp for a in averages],
            [BASE_TIME + timedelta(hours=h) for h in (2, 3, 4)],
        )

        for average in averages:
            self.assertEqual(average.exchange, "kraken")
            self.assertEqual(average.symbol, "BTC/USD")
            self.assertEqual(average.period_hours, 3)

    def test_period_of_one_returns_the_closes(self):

        candles = hourly_candles([10, 20, 30])

        averages = calculate_hourly_sma(candles, period_hours=1)

        self.assertEqual([a.value for a in averages], [10.0, 20.0, 30.0])

    def test_too_few_candles_gives_no_average(self):

        candles = hourly_candles([10, 20])

        self.assertEqual(calculate_hourly_sma(candles, period_hours=3), [])

    def test_empty_input_gives_empty_output(self):

        self.assertEqual(calculate_hourly_sma([], period_hours=3), [])

    def test_unsorted_input_is_sorted_by_time(self):

        candles = hourly_candles([10, 20, 30, 40])

        averages = calculate_hourly_sma(
            list(reversed(candles)), period_hours=2
        )

        self.assertEqual([a.value for a in averages], [15.0, 25.0, 35.0])

    def test_window_resets_across_a_missing_hour(self):

        # Hour 3 is missing: 0,1,2 | gap | 4,5,6
        candles = hourly_candles(
            [10, 20, 30, 999, 50, 60, 70],
            skip_hours={3},
        )

        averages = calculate_hourly_sma(candles, period_hours=3)

        self.assertEqual([a.value for a in averages], [20.0, 60.0])
        self.assertEqual(
            [a.timestamp for a in averages],
            [BASE_TIME + timedelta(hours=2), BASE_TIME + timedelta(hours=6)],
        )

    def test_invalid_periods_are_rejected(self):

        candles = hourly_candles([10, 20, 30])

        for bad_period in (0, -1, 2.0, True, "3"):
            with self.subTest(period=bad_period):
                with self.assertRaises(ValueError):
                    calculate_hourly_sma(candles, period_hours=bad_period)

    def test_mixed_exchanges_are_rejected(self):

        candles = hourly_candles([10, 20])
        candles += hourly_candles(
            [30], start=BASE_TIME + timedelta(hours=2), exchange="coinbase"
        )

        with self.assertRaises(ValueError):
            calculate_hourly_sma(candles, period_hours=2)

    def test_mixed_symbols_are_rejected(self):

        candles = hourly_candles([10, 20])
        candles += hourly_candles(
            [30], start=BASE_TIME + timedelta(hours=2), symbol="ETH/USD"
        )

        with self.assertRaises(ValueError):
            calculate_hourly_sma(candles, period_hours=2)

    def test_duplicate_timestamps_are_rejected(self):

        candles = hourly_candles([10, 20])
        candles.append(replace(candles[1], close=21))

        with self.assertRaises(ValueError):
            calculate_hourly_sma(candles, period_hours=2)

    def test_naive_timestamps_are_rejected(self):

        candles = hourly_candles([10, 20])
        candles[1] = replace(candles[1], timestamp=datetime(2026, 11, 14, 1))

        with self.assertRaises(ValueError):
            calculate_hourly_sma(candles[1:], period_hours=1)

    def test_non_positive_closes_are_rejected(self):

        candles = hourly_candles([10, 0, 30])

        with self.assertRaises(ValueError):
            calculate_hourly_sma(candles, period_hours=2)


if __name__ == "__main__":
    unittest.main()
