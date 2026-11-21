import unittest
from datetime import timedelta

from src.analysis.indicators import SimpleMovingAverage
from src.strategies.sma_crossover import generate_sma_crossover_signals
from tests.helpers import BASE_TIME


def averages(
    values: list[float | None],
    period_hours: int,
    exchange: str = "kraken",
    symbol: str = "BTC/USD",
) -> list[SimpleMovingAverage]:
    """
    Build hourly SMA values. A None entry means there is no value for
    that hour (a gap).
    """

    return [
        SimpleMovingAverage(
            exchange=exchange,
            symbol=symbol,
            timestamp=BASE_TIME + timedelta(hours=offset),
            period_hours=period_hours,
            value=value,
        )
        for offset, value in enumerate(values)
        if value is not None
    ]


class TestSmaCrossoverSignals(unittest.TestCase):

    def test_upward_then_downward_cross(self):

        fast = averages([9, 11, 12, 9], period_hours=2)
        slow = averages([10, 10, 10, 10], period_hours=5)

        signals = generate_sma_crossover_signals(fast, slow)

        self.assertEqual(
            [(s.action, s.candle_timestamp) for s in signals],
            [
                ("ENTER_LONG", BASE_TIME + timedelta(hours=1)),
                ("EXIT_LONG", BASE_TIME + timedelta(hours=3)),
            ],
        )

        entry = signals[0]
        self.assertEqual(entry.fast_sma, 11)
        self.assertEqual(entry.slow_sma, 10)
        self.assertEqual(entry.exchange, "kraken")
        self.assertEqual(entry.symbol, "BTC/USD")

    def test_no_signal_on_first_value(self):

        # Fast starts above slow: that is not a cross, there is no
        # earlier hour to compare with.
        fast = averages([11, 12], period_hours=2)
        slow = averages([10, 10], period_hours=5)

        self.assertEqual(generate_sma_crossover_signals(fast, slow), [])

    def test_downward_cross_without_position_is_ignored(self):

        # Long-only: an exit makes no sense before an entry.
        fast = averages([11, 9], period_hours=2)
        slow = averages([10, 10], period_hours=5)

        self.assertEqual(generate_sma_crossover_signals(fast, slow), [])

    def test_touch_then_cross_counts_as_one_entry(self):

        fast = averages([9, 10, 11], period_hours=2)
        slow = averages([10, 10, 10], period_hours=5)

        signals = generate_sma_crossover_signals(fast, slow)

        self.assertEqual([s.action for s in signals], ["ENTER_LONG"])
        self.assertEqual(
            signals[0].candle_timestamp, BASE_TIME + timedelta(hours=2)
        )

    def test_touching_without_crossing_gives_no_signal(self):

        fast = averages([9, 10, 9], period_hours=2)
        slow = averages([10, 10, 10], period_hours=5)

        self.assertEqual(generate_sma_crossover_signals(fast, slow), [])

    def test_no_cross_is_inferred_across_a_gap(self):

        # Hour 2 is missing. Fast is below at hour 1 and above at hour 3,
        # but we cannot know when it crossed, so no signal.
        fast = averages([9, 9, None, 11, 12], period_hours=2)
        slow = averages([10, 10, None, 10, 10], period_hours=5)

        self.assertEqual(generate_sma_crossover_signals(fast, slow), [])

    def test_only_hours_with_both_averages_are_compared(self):

        # The slow SMA starts later (it needs more candles).
        fast = averages([1, 2, 9, 11], period_hours=2)
        slow = averages([None, None, 10, 10], period_hours=5)

        signals = generate_sma_crossover_signals(fast, slow)

        self.assertEqual([s.action for s in signals], ["ENTER_LONG"])
        self.assertEqual(
            signals[0].candle_timestamp, BASE_TIME + timedelta(hours=3)
        )

    def test_empty_inputs_give_no_signals(self):

        some = averages([10], period_hours=5)

        self.assertEqual(generate_sma_crossover_signals([], some), [])
        self.assertEqual(generate_sma_crossover_signals(some, []), [])

    def test_fast_period_must_be_shorter_than_slow(self):

        fast = averages([9, 11], period_hours=5)
        slow = averages([10, 10], period_hours=5)

        with self.assertRaises(ValueError):
            generate_sma_crossover_signals(fast, slow)

    def test_mixed_exchanges_are_rejected(self):

        fast = averages([9, 11], period_hours=2)
        slow = averages([10, 10], period_hours=5, exchange="coinbase")

        with self.assertRaises(ValueError):
            generate_sma_crossover_signals(fast, slow)

    def test_mixed_symbols_are_rejected(self):

        fast = averages([9, 11], period_hours=2)
        slow = averages([10, 10], period_hours=5, symbol="ETH/USD")

        with self.assertRaises(ValueError):
            generate_sma_crossover_signals(fast, slow)

    def test_mixed_periods_are_rejected(self):

        fast = averages([9], period_hours=2) + [
            SimpleMovingAverage(
                exchange="kraken",
                symbol="BTC/USD",
                timestamp=BASE_TIME + timedelta(hours=1),
                period_hours=3,
                value=11,
            )
        ]
        slow = averages([10, 10], period_hours=5)

        with self.assertRaises(ValueError):
            generate_sma_crossover_signals(fast, slow)

    def test_duplicate_timestamps_are_rejected(self):

        fast = averages([9, 11], period_hours=2)
        fast.append(fast[1])
        slow = averages([10, 10], period_hours=5)

        with self.assertRaises(ValueError):
            generate_sma_crossover_signals(fast, slow)


if __name__ == "__main__":
    unittest.main()
