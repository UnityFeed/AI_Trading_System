import unittest
from datetime import datetime, timedelta, timezone

from src.backtesting.engine import BacktestResult, Trade
from src.backtesting.search import StrategySpec
from src.backtesting.walk_forward import (
    chain_returns,
    curve_stats,
    stitched_curve,
    summarize,
    walk_forward,
)


U = timezone.utc


def day(year, month=1, d=1):
    return datetime(year, month, d, tzinfo=U)


def result(points, entries=()):
    """BacktestResult with an equity curve and trades entered at `entries`."""

    trades = [
        Trade(t, 1.0, t + timedelta(days=1), 1.0, 0.0, "signal") for t in entries
    ]
    return BacktestResult(
        start=points[0][0], end=points[-1][0], final_equity=points[-1][1],
        max_drawdown_pct=0.0, exposure_pct=0.0, trades=trades,
        equity_curve=list(points),
    )


SPEC_A = StrategySpec("none", "rsi<30", "none", "rsi>70", None)
SPEC_B = StrategySpec("none", "rsi<40", "none", "rsi>70", None)


class TestSummaries(unittest.TestCase):

    def test_years_carry_on_from_the_previous_year_end(self):

        run = result([
            (day(2020), 1.0), (day(2020, 6), 2.0), (day(2020, 12), 1.5),
            (day(2021), 3.0), (day(2021, 6), 1.5),
        ], entries=[day(2020, 2), day(2021, 3)])

        summary = summarize(run)

        y2020, y2021 = summary.years[2020], summary.years[2021]
        self.assertAlmostEqual(y2020.return_pct, 50.0)
        self.assertAlmostEqual(y2020.max_drawdown_pct, 25.0)  # 2.0 -> 1.5
        self.assertAlmostEqual(y2021.return_pct, 0.0)         # 1.5 -> 3.0 -> 1.5
        self.assertAlmostEqual(y2021.max_drawdown_pct, 50.0)
        self.assertEqual((y2020.trades, y2021.trades), (1, 1))

        self.assertAlmostEqual(summary.before(2021).return_pct, 50.0)
        self.assertAlmostEqual(summary.to_year_end[2021].max_drawdown_pct, 50.0)
        self.assertEqual(summary.to_year_end[2021].trades, 2)

    def test_summary_needs_an_equity_curve(self):

        empty = BacktestResult(day(2020), day(2021), 1.0, 0.0, 0.0)
        with self.assertRaises(ValueError):
            summarize(empty)

    def test_curve_stats_window(self):

        curve = [(day(2020), 1.0), (day(2020, 6), 2.0), (day(2021), 1.0)]

        stats = curve_stats(curve, day(2020, 3), day(2021, 6), trades=0)

        self.assertAlmostEqual(stats.return_pct, 0.0)  # base 1.0 before March
        self.assertAlmostEqual(stats.max_drawdown_pct, 50.0)
        self.assertIsNone(curve_stats(curve, day(2022), day(2023), 0))


class TestWalkForward(unittest.TestCase):

    def test_each_year_uses_only_earlier_years(self):

        # A is great in 2019 and awful in 2020; B is the opposite.
        a = result([
            (day(2019), 1.0), (day(2019, 6), 1.5), (day(2019, 12), 2.0),
            (day(2020), 2.0), (day(2020, 12), 1.0),
            (day(2021), 1.0), (day(2021, 12), 1.1),
        ], entries=[day(2019, 2), day(2020, 2), day(2021, 2)])
        b = result([
            (day(2019), 1.0), (day(2019, 6), 0.8), (day(2019, 12), 0.9),
            (day(2020), 0.9), (day(2020, 12), 2.7),
            (day(2021), 2.7), (day(2021, 12), 2.7),
        ], entries=[day(2019, 2), day(2020, 2), day(2021, 2)])
        held = result([
            (day(2019), 1.0), (day(2019, 12), 1.0),
            (day(2020), 1.0), (day(2020, 12), 1.0),
            (day(2021), 1.0), (day(2021, 12), 1.0),
        ])

        picks = walk_forward(
            {SPEC_A: summarize(a), SPEC_B: summarize(b)},
            summarize(held), [2020, 2021], min_trades_per_year=0.5,
        )

        # 2020 is chosen on 2019 only -> A (and A then loses 50% in 2020).
        self.assertEqual(picks[0].year, 2020)
        self.assertEqual(picks[0].spec, SPEC_A)
        self.assertAlmostEqual(picks[0].strategy.return_pct, -50.0)
        # 2021 is chosen on 2019-2020 -> B overall did better.
        self.assertEqual(picks[1].spec, SPEC_B)

        self.assertAlmostEqual(
            chain_returns([p.strategy for p in picks]), (0.5 * 1.0 - 1) * 100
        )

        stitched = stitched_curve(picks, {SPEC_A: a, SPEC_B: b})
        self.assertAlmostEqual(stitched[-1][1], 0.5)

    def test_combinations_with_too_few_trades_are_not_picked(self):

        busy = result([(day(2019), 1.0), (day(2019, 12), 1.1), (day(2020, 12), 1.0)],
                      entries=[day(2019, 3)])
        idle = result([(day(2019), 1.0), (day(2019, 12), 5.0), (day(2020, 12), 5.0)])
        held = result([(day(2019), 1.0), (day(2019, 12), 1.0), (day(2020, 12), 1.0)])

        picks = walk_forward(
            {SPEC_A: summarize(busy), SPEC_B: summarize(idle)},
            summarize(held), [2020], min_trades_per_year=0.5,
        )

        self.assertEqual(picks[0].spec, SPEC_A)


if __name__ == "__main__":
    unittest.main()
