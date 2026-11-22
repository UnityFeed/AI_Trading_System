import unittest
from dataclasses import replace
from datetime import datetime, timezone

from src.analysis.primary_history import PRIMARY_LABEL, ContinuousHistory
from src.backtesting.conditions import EXITS, TREND_FILTERS, TRIGGERS, VOLUME_FILTERS
from src.backtesting.engine import CostSettings, run_backtest
from src.backtesting.market import build_market
from src.backtesting.report import (
    btc_vs_hold, signals, start_year_table, strategy_report, strategy_state, trade_markers_from_report,
)
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


class TestStartDate(unittest.TestCase):

    def setUp(self):
        self.market = make_market()  # 2025-12-30 .. 2026-01-04, hourly

    def test_report_from_a_start_date_matches_a_run_on_that_window(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        report = strategy_report(self.market, DEFINITION, NO_COSTS, start=start)

        window = self.market.index_range(start, datetime(9999, 1, 1, tzinfo=timezone.utc))
        entry, exit_signal = signals(self.market, DEFINITION)
        direct = run_backtest(self.market, window, entry, exit_signal, None, NO_COSTS)

        self.assertEqual(report["start"], "2026-01-01")
        self.assertEqual(report["summary"]["start"], start.isoformat())
        self.assertAlmostEqual(report["summary"]["total_return_pct"], round(direct.total_return_pct, 2))
        self.assertTrue(all(t["entry_time"] >= start.isoformat() for t in report["trades"]))

    def test_btc_vs_hold_is_the_ratio_of_end_values(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        report = strategy_report(self.market, DEFINITION, NO_COSTS, start=start)
        ratio = (1 + report["summary"]["total_return_pct"] / 100) / (1 + report["buy_and_hold"]["total_return_pct"] / 100)
        self.assertAlmostEqual(report["summary"]["btc_vs_hold"], round(ratio, 3), places=2)

    def test_start_year_table_has_one_row_per_full_year(self):
        rows = start_year_table(self.market, DEFINITION, NO_COSTS)
        self.assertEqual([r["year"] for r in rows], [2026])
        self.assertIn("btc_vs_hold", rows[0])

    def test_start_after_the_data_is_rejected(self):
        with self.assertRaises(ValueError):
            strategy_report(self.market, DEFINITION, NO_COSTS, start=datetime(2030, 1, 1, tzinfo=timezone.utc))

    def test_btc_vs_hold_without_value(self):
        empty = type("R", (), {"final_equity": 1.0})()
        zero = type("R", (), {"final_equity": 0.0})()
        self.assertEqual(btc_vs_hold(empty, zero), 0.0)


def prefix(market, k):
    """The market as it looked when only its first k candles existed."""
    return replace(market, candles=market.candles[:k], rows=market.rows[:k],
                   tradeable=market.tradeable[:k], consecutive=market.consecutive[:k])


class TestStrategyState(unittest.TestCase):

    def setUp(self):
        self.market = make_market()

    def test_signals_are_carried_out_at_the_next_open(self):
        """A BUY/SELL signal at a close must show up as a trade one candle later."""
        seen = {"BUY": 0, "SELL": 0}
        for k in range(40, len(self.market.candles) - 1):
            now = strategy_state(prefix(self.market, k), DEFINITION, NO_COSTS)
            if not now["signal"]:
                continue
            action = now["signal"]["action"]
            seen[action] += 1
            later = strategy_state(prefix(self.market, k + 1), DEFINITION, NO_COSTS)
            next_open = self.market.candles[k].timestamp.isoformat()
            if action == "BUY":
                self.assertEqual(later["position"]["entry_time"], next_open)
            else:
                self.assertIsNone(later["position"])
                self.assertEqual(later["last_closed_trade"]["exit_time"], next_open)
        self.assertGreater(seen["BUY"], 0)
        self.assertGreater(seen["SELL"], 0)

    def test_open_position_matches_the_backtest(self):
        # Find a moment where the strategy holds BTC.
        for k in range(40, len(self.market.candles)):
            state = strategy_state(prefix(self.market, k), DEFINITION, NO_COSTS)
            if state["position"]:
                break
        else:
            self.fail("the test market never holds a position")

        report = strategy_report(prefix(self.market, k), DEFINITION, NO_COSTS)
        open_trade = report["trades"][-1]
        self.assertTrue(open_trade["open"])
        self.assertEqual(state["position"]["entry_time"], open_trade["entry_time"])
        self.assertAlmostEqual(state["position"]["result_if_sold_pct"], open_trade["return_pct"])

    def test_rules_and_recent_trades(self):
        state = strategy_state(self.market, DEFINITION, NO_COSTS)

        self.assertEqual([r["role"] for r in state["rules"]], ["Trend filter", "Buy trigger", "Sell rule"])
        self.assertLessEqual(len(state["recent_trades"]), 5)
        if state["recent_trades"]:
            newest = state["recent_trades"][0]
            self.assertEqual(newest, state["last_closed_trade"])


if __name__ == "__main__":
    unittest.main()
