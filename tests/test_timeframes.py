import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from src.analysis.timeframes import (
    aggregate_hourly_candles,
    period_start,
    split_into_runs,
)
from tests.helpers import BASE_TIME, hourly_candles


# BASE_TIME is 2026-11-14 00:00 UTC, the start of a day.


def varied_candles(hours: int, start=BASE_TIME):
    """Hourly candles with distinct open/high/low/close/volume values."""

    candles = hourly_candles([100 + i for i in range(hours)], start=start)

    return [
        replace(
            candle,
            open=100 + i,
            high=110 + i,
            low=90 + i,
            close=101 + i,
            volume=1 + i,
        )
        for i, candle in enumerate(candles)
    ]


class TestPeriodStart(unittest.TestCase):

    def test_four_hour_boundaries(self):

        for hour, expected in ((0, 0), (3, 0), (4, 4), (7, 4), (23, 20)):
            with self.subTest(hour=hour):
                timestamp = BASE_TIME.replace(hour=hour)
                self.assertEqual(
                    period_start(timestamp, "4h"),
                    BASE_TIME.replace(hour=expected),
                )

    def test_day_boundary_is_utc_midnight(self):

        # 00:30 in UTC+2 is 22:30 UTC on the previous day.
        plus_two = timezone(timedelta(hours=2))
        local = datetime(2026, 11, 15, 0, 30, tzinfo=plus_two)

        self.assertEqual(period_start(local, "1d"), BASE_TIME)


class TestAggregateHourlyCandles(unittest.TestCase):

    def test_daily_candle_ohlcv(self):

        result = aggregate_hourly_candles(varied_candles(24), "1d")

        self.assertEqual(len(result.candles), 1)
        self.assertEqual(result.incomplete_periods, [])

        day = result.candles[0]
        self.assertEqual(day.timestamp, BASE_TIME)
        self.assertEqual(day.open, 100)        # first hour's open
        self.assertEqual(day.high, 110 + 23)   # highest high
        self.assertEqual(day.low, 90)          # lowest low
        self.assertEqual(day.close, 101 + 23)  # last hour's close
        self.assertEqual(day.volume, sum(range(1, 25)))
        self.assertEqual(day.exchange, "kraken")
        self.assertEqual(day.symbol, "BTC/USD")

    def test_four_hour_candles(self):

        result = aggregate_hourly_candles(varied_candles(24), "4h")

        self.assertEqual(len(result.candles), 6)
        self.assertEqual(
            [c.timestamp.hour for c in result.candles],
            [0, 4, 8, 12, 16, 20],
        )

        second = result.candles[1]  # hours 4-7
        self.assertEqual(second.open, 104)
        self.assertEqual(second.high, 117)
        self.assertEqual(second.low, 94)
        self.assertEqual(second.close, 108)
        self.assertEqual(second.volume, 5 + 6 + 7 + 8)

    def test_one_hour_returns_the_same_candles(self):

        candles = varied_candles(5)

        result = aggregate_hourly_candles(candles, "1h")

        self.assertEqual(result.candles, candles)

    def test_period_with_a_missing_hour_is_skipped_and_reported(self):

        candles = varied_candles(8)
        del candles[5]  # 05:00 missing, so 04:00-08:00 is incomplete

        result = aggregate_hourly_candles(candles, "4h")

        self.assertEqual([c.timestamp.hour for c in result.candles], [0])
        self.assertEqual(len(result.incomplete_periods), 1)

        skipped = result.incomplete_periods[0]
        self.assertEqual(skipped.start, BASE_TIME.replace(hour=4))
        self.assertEqual(skipped.hours_present, 3)
        self.assertEqual(skipped.hours_expected, 4)

    def test_partial_first_and_last_periods_are_skipped(self):

        # Data starts at 02:00 and stops at 09:00 (exclusive):
        # 00-04 and 08-12 are incomplete, only 04-08 is complete.
        candles = varied_candles(7, start=BASE_TIME.replace(hour=2))

        result = aggregate_hourly_candles(candles, "4h")

        self.assertEqual([c.timestamp.hour for c in result.candles], [4])
        self.assertEqual(
            [p.start.hour for p in result.incomplete_periods], [0, 8]
        )

    def test_unsorted_input_gives_the_same_result(self):

        candles = varied_candles(24)

        self.assertEqual(
            aggregate_hourly_candles(list(reversed(candles)), "1d"),
            aggregate_hourly_candles(candles, "1d"),
        )

    def test_empty_input(self):

        result = aggregate_hourly_candles([], "1d")

        self.assertEqual(result.candles, [])
        self.assertEqual(result.incomplete_periods, [])

    def test_unsupported_timeframe_is_rejected(self):

        with self.assertRaises(ValueError):
            aggregate_hourly_candles(varied_candles(3), "3h")

    def test_mixed_exchanges_are_rejected(self):

        candles = varied_candles(4)
        candles[2] = replace(candles[2], exchange="bitstamp")

        with self.assertRaises(ValueError):
            aggregate_hourly_candles(candles, "4h")

    def test_mixed_symbols_are_rejected(self):

        candles = varied_candles(4)
        candles[2] = replace(candles[2], symbol="ETH/USD")

        with self.assertRaises(ValueError):
            aggregate_hourly_candles(candles, "4h")

    def test_duplicate_hours_are_rejected(self):

        candles = varied_candles(4)
        candles.append(candles[1])

        with self.assertRaises(ValueError):
            aggregate_hourly_candles(candles, "4h")

    def test_unaligned_and_naive_timestamps_are_rejected(self):

        unaligned = varied_candles(2)
        unaligned[1] = replace(
            unaligned[1], timestamp=unaligned[1].timestamp + timedelta(minutes=5)
        )

        naive = varied_candles(1)
        naive[0] = replace(naive[0], timestamp=datetime(2026, 11, 14))

        for candles in (unaligned, naive):
            with self.assertRaises(ValueError):
                aggregate_hourly_candles(candles, "1d")


class TestSplitIntoRuns(unittest.TestCase):

    def test_consecutive_candles_form_one_run(self):

        runs = split_into_runs(varied_candles(5), "1h")

        self.assertEqual([len(run) for run in runs], [5])

    def test_gaps_start_new_runs(self):

        candles = hourly_candles(list(range(10)), skip_hours={3, 4, 7})

        runs = split_into_runs(list(reversed(candles)), "1h")

        self.assertEqual([len(run) for run in runs], [3, 2, 2])
        self.assertEqual(runs[1][0].timestamp, BASE_TIME.replace(hour=5))

    def test_daily_runs(self):

        days = aggregate_hourly_candles(
            varied_candles(24 * 4), "1d"
        ).candles
        del days[2]

        runs = split_into_runs(days, "1d")

        self.assertEqual([len(run) for run in runs], [2, 1])

    def test_candles_not_on_period_start_are_rejected(self):

        with self.assertRaises(ValueError):
            split_into_runs(varied_candles(3), "1d")

    def test_empty_and_unknown_timeframe(self):

        self.assertEqual(split_into_runs([], "4h"), [])

        with self.assertRaises(ValueError):
            split_into_runs(varied_candles(2), "2h")


if __name__ == "__main__":
    unittest.main()
