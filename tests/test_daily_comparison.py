import unittest
from dataclasses import replace
from datetime import timedelta

from src.analysis.daily_comparison import compare_daily_candles
from tests.helpers import BASE_TIME, hourly_candles


def days(closes, exchange="kraken"):
    """Daily candles: one per day starting at BASE_TIME."""

    hourly = hourly_candles(closes, exchange=exchange)

    return [
        replace(candle, timestamp=BASE_TIME + timedelta(days=i))
        for i, candle in enumerate(hourly)
    ]


class TestCompareDailyCandles(unittest.TestCase):

    def test_identical_days_have_no_difference(self):

        comparison = compare_daily_candles(days([100, 200]), days([100, 200]))

        self.assertEqual(comparison.exchange, "kraken")
        self.assertEqual(len(comparison.matched), 2)
        self.assertEqual(comparison.days_above(0.0), [])

        for day in comparison.matched:
            self.assertEqual(day.max_price_diff_pct, 0.0)
            self.assertEqual(day.volume_diff_pct, 0.0)

    def test_differences_are_percentages_of_the_exchange_value(self):

        ours = days([100])
        theirs = [replace(days([100])[0], high=80, close=125, volume=2.0)]

        day = compare_daily_candles(ours, theirs).matched[0]

        self.assertAlmostEqual(day.price_diff_pct["high"], 25.0)
        self.assertAlmostEqual(day.price_diff_pct["close"], -20.0)
        self.assertAlmostEqual(day.price_diff_pct["open"], 0.0)
        self.assertAlmostEqual(day.max_price_diff_pct, 25.0)
        self.assertAlmostEqual(day.volume_diff_pct, -50.0)

    def test_unmatched_days_are_listed_per_side(self):

        ours = days([100, 101, 102])
        theirs = days([100, 101, 102, 103])
        del ours[1]

        comparison = compare_daily_candles(ours, theirs)

        self.assertEqual(len(comparison.matched), 2)
        self.assertEqual(
            comparison.reference_only,
            [BASE_TIME + timedelta(days=1), BASE_TIME + timedelta(days=3)],
        )
        self.assertEqual(comparison.derived_only, [])

    def test_worst_days_and_threshold(self):

        ours = days([100, 100, 100])
        theirs = days([100, 99, 90])

        comparison = compare_daily_candles(ours, theirs)

        worst = comparison.worst_days(2)
        self.assertEqual(
            [d.timestamp for d in worst],
            [BASE_TIME + timedelta(days=2), BASE_TIME + timedelta(days=1)],
        )
        self.assertEqual(len(comparison.days_above(5.0)), 1)

    def test_zero_reference_volume_gives_no_volume_difference(self):

        ours = days([100])
        theirs = [replace(days([100])[0], volume=0.0)]

        day = compare_daily_candles(ours, theirs).matched[0]

        self.assertIsNone(day.volume_diff_pct)

    def test_different_exchanges_are_rejected(self):

        with self.assertRaises(ValueError):
            compare_daily_candles(days([100]), days([100], exchange="coinbase"))

    def test_duplicate_days_are_rejected(self):

        ours = days([100])

        with self.assertRaises(ValueError):
            compare_daily_candles(ours + ours, days([100]))


if __name__ == "__main__":
    unittest.main()
