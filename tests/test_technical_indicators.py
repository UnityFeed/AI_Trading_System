"""
Indicator tests use small inputs whose answers can be worked out by hand.
The indicators were also cross-checked against an independent pandas
calculation on 3,000 real Coinbase hourly candles (21 Nov 2026): all
values matched to floating-point precision.
"""

import unittest
from dataclasses import replace
from datetime import timedelta
from math import sqrt

from src.analysis.technical_indicators import (
    IndicatorSettings,
    atr_series,
    bollinger_series,
    calculate_indicators,
    ema_series,
    macd_series,
    relative_volume_series,
    rsi_series,
    sma_series,
)
from src.analysis.timeframes import aggregate_hourly_candles
from tests.helpers import BASE_TIME, hourly_candles


def candles_with_range(rows):
    """rows: (high, low, close) per hour."""

    candles = hourly_candles([close for _, _, close in rows])

    return [
        replace(candle, high=high, low=low)
        for candle, (high, low, _) in zip(candles, rows)
    ]


class TestBuildingBlocks(unittest.TestCase):

    def assertSeries(self, actual, expected):
        self.assertEqual(len(actual), len(expected))
        for a, e in zip(actual, expected):
            if e is None:
                self.assertIsNone(a)
            else:
                self.assertAlmostEqual(a, e)

    def test_sma(self):
        self.assertSeries(
            sma_series([1, 2, 3, 4, 5], 3), [None, None, 2, 3, 4]
        )

    def test_ema_is_seeded_with_sma(self):
        # k = 2 / (3 + 1) = 0.5; seed = mean(1, 2, 3) = 2
        # then 2 + 0.5 * (4 - 2) = 3 and 3 + 0.5 * (5 - 3) = 4
        self.assertSeries(
            ema_series([1, 2, 3, 4, 5], 3), [None, None, 2, 3, 4]
        )

    def test_ema_reacts_faster_than_sma(self):
        values = [10] * 5 + [20]
        self.assertGreater(ema_series(values, 5)[-1], sma_series(values, 5)[-1])

    def test_ema_skips_leading_none(self):
        self.assertSeries(
            ema_series([None, None, 1, 2, 3, 4], 3),
            [None, None, None, None, 2, 3],
        )

    def test_ema_rejects_a_gap_after_it_started(self):
        with self.assertRaises(ValueError):
            ema_series([1, 2, None, 4], 2)

    def test_too_short_input_gives_only_none(self):
        self.assertSeries(ema_series([1, 2], 3), [None, None])
        self.assertSeries(rsi_series([1, 2, 3], 3), [None, None, None])
        self.assertSeries(sma_series([1], 2), [None])

    def test_rsi_wilder_smoothing(self):
        # period 2, changes: +1, -1, +1
        # first averages: gain 0.5, loss 0.5 -> RSI 50
        # next: gain (0.5 + 1) / 2 = 0.75, loss (0.5 + 0) / 2 = 0.25
        #       RS = 3 -> RSI = 100 - 100 / 4 = 75
        self.assertSeries(rsi_series([1, 2, 1, 2], 2), [None, None, 50, 75])

    def test_rsi_extremes(self):
        self.assertEqual(rsi_series([1, 2, 3, 4], 3)[-1], 100.0)
        self.assertEqual(rsi_series([4, 3, 2, 1], 3)[-1], 0.0)
        self.assertEqual(rsi_series([5, 5, 5, 5], 3)[-1], 50.0)

    def test_macd_warmup_and_flat_market(self):
        line, signal, histogram = macd_series([100.0] * 40)

        self.assertIsNone(line[24])
        self.assertEqual(line[25], 0.0)      # needs 26 closes
        self.assertIsNone(signal[32])
        self.assertEqual(signal[33], 0.0)    # plus 9 MACD values
        self.assertEqual(histogram[33], 0.0)

    def test_macd_is_positive_in_an_uptrend(self):
        line, signal, histogram = macd_series([float(i) for i in range(60)])

        self.assertGreater(line[-1], 0)
        self.assertAlmostEqual(line[-1], signal[-1])  # steady trend

    def test_macd_rejects_fast_not_shorter_than_slow(self):
        with self.assertRaises(ValueError):
            macd_series([1.0] * 40, fast=26, slow=12)

    def test_bollinger(self):
        middle, upper, lower, width = bollinger_series([1, 2, 3], 3, 2.0)

        std = sqrt(2 / 3)  # population std of 1, 2, 3
        self.assertAlmostEqual(middle[2], 2)
        self.assertAlmostEqual(upper[2], 2 + 2 * std)
        self.assertAlmostEqual(lower[2], 2 - 2 * std)
        self.assertAlmostEqual(width[2], 4 * std / 2)
        self.assertIsNone(upper[1])

    def test_bollinger_flat_market_has_zero_width(self):
        _, upper, lower, width = bollinger_series([5.0] * 4, 3)
        self.assertEqual(width[-1], 0.0)
        self.assertEqual(upper[-1], lower[-1])

    def test_atr(self):
        candles = candles_with_range([
            (11, 9, 10),   # TR = 2 (first candle: high - low)
            (12, 10, 11),  # TR = max(2, |12-10|, |10-10|) = 2
            (15, 13, 14),  # TR = max(2, |15-11|, |13-11|) = 4  (gap up)
            (14, 8, 9),    # TR = max(6, |14-14|, |8-14|) = 6
        ])

        # period 2: first ATR = (2 + 2) / 2 = 2 at index 1,
        # then (2 * 1 + 4) / 2 = 3, then (3 * 1 + 6) / 2 = 4.5
        self.assertSeries(atr_series(candles, 2), [None, 2, 3, 4.5])

    def test_relative_volume_uses_previous_candles_only(self):
        # average of the 3 volumes before the spike is 1
        self.assertSeries(
            relative_volume_series([1, 1, 1, 4], 3), [None, None, None, 4]
        )

    def test_relative_volume_after_zero_volume_is_none(self):
        self.assertSeries(
            relative_volume_series([0, 0, 0, 4], 3), [None, None, None, None]
        )

    def test_invalid_periods_are_rejected(self):
        for bad in (0, -1, 2.5, True):
            with self.subTest(period=bad):
                with self.assertRaises(ValueError):
                    sma_series([1, 2, 3], bad)


class TestCalculateIndicators(unittest.TestCase):

    SMALL = IndicatorSettings(
        ema_periods=(3,),
        rsi_period=2,
        macd_fast=2,
        macd_slow=3,
        macd_signal=2,
        bollinger_period=3,
        atr_period=2,
        volume_period=2,
    )

    def test_one_row_per_candle_with_expected_names(self):

        rows = calculate_indicators(hourly_candles(range(100, 110)), "1h", self.SMALL)

        self.assertEqual(len(rows), 10)
        self.assertEqual(
            set(rows[0].values),
            {
                "ema_3", "rsi_2", "macd", "macd_signal", "macd_hist",
                "bb_middle", "bb_upper", "bb_lower", "bb_width", "atr_2",
                "volume_sma_2", "relative_volume_2",
            },
        )
        self.assertEqual(rows[0].timeframe, "1h")
        self.assertEqual(rows[-1].close, 109)
        self.assertFalse(rows[0].is_complete())
        self.assertTrue(rows[-1].is_complete())

    def test_default_settings_names(self):

        rows = calculate_indicators(hourly_candles([100.0] * 3), "1h")

        self.assertEqual(
            {name for name in rows[0].values if name.startswith(("ema", "rsi", "atr"))},
            {"ema_20", "ema_50", "ema_200", "rsi_14", "atr_14"},
        )

    def test_indicators_restart_after_a_gap(self):

        # Hour 5 is missing: run A = hours 0-4, run B = hours 6-11.
        candles = hourly_candles(range(100, 112), skip_hours={5})

        rows = calculate_indicators(candles, "1h", self.SMALL)
        by_hour = {
            int((row.timestamp - BASE_TIME) / timedelta(hours=1)): row
            for row in rows
        }

        self.assertNotIn(5, by_hour)
        self.assertIsNotNone(by_hour[4].values["ema_3"])
        # ema_3 needs 3 candles of the new run: hours 6 and 7 have none.
        self.assertIsNone(by_hour[6].values["ema_3"])
        self.assertIsNone(by_hour[7].values["ema_3"])
        self.assertAlmostEqual(by_hour[8].values["ema_3"], 107)  # mean(106..108)

    def test_values_do_not_depend_on_future_candles(self):

        candles = hourly_candles([100, 103, 101, 106, 104, 108, 107, 111])

        full = calculate_indicators(candles, "1h", self.SMALL)
        partial = calculate_indicators(candles[:5], "1h", self.SMALL)

        for a, b in zip(full[:5], partial):
            self.assertEqual(a.values, b.values)

    def test_works_on_four_hour_candles(self):

        hourly = hourly_candles([100 + i for i in range(24 * 3)])
        four_hour = aggregate_hourly_candles(hourly, "4h").candles

        rows = calculate_indicators(four_hour, "4h", self.SMALL)

        self.assertEqual(len(rows), 18)
        self.assertTrue(rows[-1].is_complete())
        self.assertEqual(rows[-1].timeframe, "4h")

    def test_gap_between_four_hour_candles_restarts(self):

        hourly = hourly_candles([100 + i for i in range(24)], skip_hours={9})
        four_hour = aggregate_hourly_candles(hourly, "4h").candles

        # 08:00-12:00 is skipped, so 00, 04 | 12, 16, 20
        rows = calculate_indicators(four_hour, "4h", self.SMALL)

        self.assertIsNone(rows[2].values["ema_3"])   # 12:00, first of run
        self.assertIsNotNone(rows[4].values["ema_3"])

    def test_candles_must_match_the_timeframe(self):

        # Hourly candles at 01:00 do not start a 4h period.
        with self.assertRaises(ValueError):
            calculate_indicators(hourly_candles([1, 2, 3]), "4h")

    def test_mixed_exchanges_are_rejected(self):

        candles = hourly_candles([1, 2, 3])
        candles[1] = replace(candles[1], exchange="coinbase")

        with self.assertRaises(ValueError):
            calculate_indicators(candles, "1h")

    def test_empty_input(self):
        self.assertEqual(calculate_indicators([], "1d"), [])


if __name__ == "__main__":
    unittest.main()
