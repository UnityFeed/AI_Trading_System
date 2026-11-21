import unittest
from dataclasses import replace
from datetime import datetime, timezone

from src.analysis.primary_history import PRIMARY_LABEL, ContinuousHistory
from src.backtesting.conditions import EXITS, TREND_FILTERS, TRIGGERS, VOLUME_FILTERS
from src.backtesting.engine import CostSettings, run_backtest
from src.backtesting.market import build_market
from src.backtesting.report import signals, strategy_report, trade_markers_from_report
from src.backtesting.search import StrategySpec
from src.strategies.registry import (
    ACTIVE_STRATEGY_ID, STRATEGIES, StrategyDefinition, active_strategy, get_strategy,
)
from tests.helpers import hourly_candles


class TestRegistry(unittest.TestCase):

    def test_every_strategy_uses_known_building_blocks(self):
        for s in STRATEGIES:
            with self.subTest(strategy=s.id):
                self.assertIn(s.spec.trend, TREND_FILTERS)
                self.assertIn(s.spec.trigger, TRIGGERS)
                self.assertIn(s.spec.volume, VOLUME_FILTERS)
                self.assertIn(s.spec.exit, EXITS)
                self.assertIn(s.timeframe, ("1h", "4h", "1d"))
                self.assertTrue(s.description and s.origin)

    def test_ids_are_unique_and_the_active_one_exists(self):
        ids = [s.id for s in STRATEGIES]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(active_strategy().id, ACTIVE_STRATEGY_ID)
        with self.assertRaises(KeyError):
            get_strategy("does-not-exist")


def make_market():
    # Two rises and falls over ~4 days of hourly candles.
    closes = []
    for _ in range(2):
        closes += [100 - i for i in range(30)] + [70 + i * 2 for i in range(30)]
    candles = [replace(c, exchange=PRIMARY_LABEL)
               for c in hourly_candles(closes, start=datetime(2025, 12, 30, tzinfo=timezone.utc))]
    hours = [c.timestamp for c in candles]
    history = ContinuousHistory(candles, {h: "kraken" for h in hours}, {h: "kraken" for h in hours}, [], [])
    return build_market(history, "1h")


DEFINITION = StrategyDefinition(
    "test-rsi", "Test RSI", "1h", StrategySpec("none", "rsi<30", "none", "rsi>70", None),
    "test", "test",
)
NO_COSTS = CostSettings(fee_pct=0.0, slippage_pct=0.0)


class TestStrategyReport(unittest.TestCase):

    def setUp(self):
        self.market = make_market()
        self.report = strategy_report(self.market, DEFINITION, NO_COSTS)

    def test_report_matches_the_engine(self):
        entry, exit_signal = signals(self.market, DEFINITION)
        direct = run_backtest(self.market, range(len(self.market.candles)), entry, exit_signal, None, NO_COSTS)

        self.assertEqual(self.report["summary"]["trades"], len(direct.trades))
        self.assertAlmostEqual(self.report["summary"]["total_return_pct"], round(direct.total_return_pct, 2))
        self.assertGreater(len(direct.trades), 0)

    def test_years_trades_and_equity(self):
        years = [y["year"] for y in self.report["years"]]
        self.assertEqual(years, [2025, 2026])
        self.assertEqual(len(self.report["equity"]), len(self.report["buy_and_hold_equity"]))
        first = self.report["trades"][0]
        self.assertLess(first["entry_time"], first["exit_time"])
        self.assertIn("optimistic", self.report["note"])

    def test_markers_skip_the_sell_of_an_open_trade(self):
        report = {"trades": [
            {"entry_time": "2026-01-01T05:00:00+00:00", "entry_price": 1, "exit_time": "2026-01-02T00:00:00+00:00",
             "exit_price": 2, "open": False},
            {"entry_time": "2026-01-03T05:00:00+00:00", "entry_price": 1, "exit_time": "2026-01-04T00:00:00+00:00",
             "exit_price": 2, "open": True},
        ]}
        markers = trade_markers_from_report(report, "1d")
        self.assertEqual([m["side"] for m in markers], ["buy", "sell", "buy"])
        self.assertEqual(markers[0]["time"], int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()))


if __name__ == "__main__":
    unittest.main()
