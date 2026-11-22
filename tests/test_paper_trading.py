import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from src.analysis.primary_history import PRIMARY_LABEL, ContinuousHistory, SourceChange
from src.backtesting.engine import CostSettings
from src.backtesting.exposure import ExposureSpec
from src.backtesting.search import StrategySpec
from src.paper_trading.store import PaperTradingStore
from src.paper_trading.trader import PaperTrader
from tests.helpers import BASE_TIME, hourly_candles


NO_COSTS = CostSettings(fee_pct=0.0, slippage_pct=0.0)
# RSI(14) on hourly candles: buy when oversold, sell when overbought.
SPEC = StrategySpec("none", "rsi<30", "none", "rsi>70", None)

# 20 falling hours (RSI -> 0), then 20 rising hours (RSI -> 100).
CLOSES = [200 - 2 * i for i in range(20)] + [162 + 3 * i for i in range(1, 21)]


def make_history(closes=CLOSES, filled_hours=()):
    candles = []
    for i, c in enumerate(hourly_candles(closes)):
        previous = closes[i - 1] if i else c.close
        candles.append(replace(
            c, exchange=PRIMARY_LABEL, open=previous,
            high=max(previous, c.close), low=min(previous, c.close),
        ))
    hours = [c.timestamp for c in candles]
    sources = {h: ("coinbase" if i in filled_hours else "kraken") for i, h in enumerate(hours)}
    changes = []
    for i in range(1, len(hours)):
        if sources[hours[i]] != sources[hours[i - 1]]:
            changes.append(SourceChange(hours[i], sources[hours[i - 1]], sources[hours[i]],
                                        candles[i - 1].close, candles[i].open))
    return ContinuousHistory(candles, sources, {h: "kraken" for h in hours}, changes, [])


class TestPaperTrader(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        folder = Path(self.temp_dir.name)
        self.store = PaperTradingStore(folder / "paper.db")
        self.kill_switch = folder / "STOP"
        self.trader = PaperTrader(self.store, SPEC, "1h", NO_COSTS, self.kill_switch)
        self.now = BASE_TIME + timedelta(hours=len(CLOSES))

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_trader(self, history=None):
        self.trader.ensure_account(BASE_TIME, cash=1000.0)
        return self.trader.step(history or make_history(), now=self.now)

    def test_one_decision_per_candle_and_buy_then_sell(self):

        self.run_trader()

        decisions = list(reversed(self.store.decisions()))
        self.assertEqual(len(decisions), len(CLOSES))

        actions = [d.action for d in decisions]
        first_buy = actions.index("BUY")
        first_sell = actions.index("SELL")
        self.assertLess(first_buy, first_sell)
        self.assertEqual(actions[first_buy + 1], "HOLD")  # filled at the next open

        fills = self.store.fills()
        self.assertEqual([f.side for f in fills], ["buy", "sell"])
        buy_hour = decisions[first_buy].candle_time + timedelta(hours=1)
        self.assertEqual(fills[0].filled_at, buy_hour)
        self.assertEqual(fills[0].price, CLOSES[first_buy])  # open = previous close

        account = self.store.get_account()
        self.assertEqual(account.btc, 0.0)
        expected = 1000.0 / fills[0].price * fills[1].price
        self.assertAlmostEqual(account.cash, expected)

    def test_running_again_adds_nothing(self):

        self.run_trader()
        count = len(self.store.decisions())
        fills = len(self.store.fills())

        report = self.run_trader()

        self.assertEqual(report.decisions, [])
        self.assertEqual(len(self.store.decisions()), count)
        self.assertEqual(len(self.store.fills()), fills)

    def test_new_candles_are_processed_incrementally(self):

        self.trader.ensure_account(BASE_TIME, cash=1000.0)
        self.trader.step(make_history(CLOSES[:25]), now=BASE_TIME + timedelta(hours=25))
        self.trader.step(make_history(), now=self.now)

        incremental = [(d.candle_time, d.action) for d in self.store.decisions()]

        other = PaperTradingStore(Path(self.temp_dir.name) / "other.db")
        trader = PaperTrader(other, SPEC, "1h", NO_COSTS, self.kill_switch)
        trader.ensure_account(BASE_TIME, cash=1000.0)
        trader.step(make_history(), now=self.now)

        self.assertEqual(incremental, [(d.candle_time, d.action) for d in other.decisions()])

    def test_kill_switch_blocks_buying(self):

        self.kill_switch.write_text("stop")
        self.run_trader()

        actions = {d.action for d in self.store.decisions()}
        self.assertIn("SKIP", actions)
        self.assertNotIn("BUY", actions)
        self.assertEqual(self.store.fills(), [])

    def test_stale_data_is_not_processed(self):

        self.trader.ensure_account(BASE_TIME, cash=1000.0)
        report = self.trader.step(make_history(), now=self.now + timedelta(hours=10))

        self.assertTrue(report.warnings)
        self.assertEqual(self.store.decisions(), [])

    def test_no_fill_on_a_filled_in_hour(self):

        history = make_history()
        self.run_trader(history)
        buy = next(d for d in reversed(self.store.decisions()) if d.action == "BUY")
        buy_index = int((buy.candle_time - BASE_TIME) / timedelta(hours=1))

        # Same data, but the hour after the buy signal came from another exchange.
        other = PaperTradingStore(Path(self.temp_dir.name) / "other.db")
        trader = PaperTrader(other, SPEC, "1h", NO_COSTS, self.kill_switch)
        trader.ensure_account(BASE_TIME, cash=1000.0)
        trader.step(make_history(filled_hours={buy_index + 1}), now=self.now)

        first_fill = other.fills()[0]
        # Not the filled-in hour, and not the reopening hour after it.
        self.assertEqual(first_fill.filled_at, buy.candle_time + timedelta(hours=3))

    def test_account_cannot_switch_strategy_silently(self):

        self.trader.ensure_account(BASE_TIME)
        other = PaperTrader(self.store, StrategySpec("none", "rsi<40", "none", "rsi>70", None), "1h")

        with self.assertRaises(RuntimeError):
            other.ensure_account(BASE_TIME)

    def test_decisions_store_what_the_strategy_saw(self):

        self.run_trader()
        decision = self.store.decisions(limit=1)[0]

        self.assertIn("rsi_14", decision.snapshot["indicators"])
        self.assertIn("trigger: rsi<30", decision.snapshot["rules"])



class TestGradedPaperTrader(unittest.TestCase):
    """A graded strategy moves the paper account to a target BTC share."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        folder = Path(self.temp_dir.name)
        self.store = PaperTradingStore(folder / "paper.db")
        self.kill_switch = folder / "STOP"
        self.now = BASE_TIME + timedelta(hours=len(CLOSES))

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_trader(self, spec, costs=NO_COSTS):
        trader = PaperTrader(self.store, spec, "1h", costs, self.kill_switch)
        trader.ensure_account(BASE_TIME, cash=1000.0)
        return trader.step(make_history(), now=self.now)

    def test_fixed_share_is_bought_once_then_held(self):

        self.run_trader(ExposureSpec("60% fixed", fixed_weight=0.6, band=0.10),
                        CostSettings(fee_pct=0.8, slippage_pct=0.05))

        decisions = list(reversed(self.store.decisions()))  # oldest first
        self.assertEqual(decisions[0].action, "BUY")
        self.assertEqual(decisions[0].snapshot["target_exposure"], 0.6)
        fills = self.store.fills()
        self.assertEqual(len(fills), 1)
        account = self.store.get_account()
        price = make_history().candles[1].open
        share = account.btc * price / (account.cash + account.btc * price)
        self.assertAlmostEqual(share, 0.6, delta=0.01)
        self.assertAlmostEqual(fills[0].fee, 600 * 0.008)
        # The price runs from 200 to 222 and back: the share drifts, never by 10 points.
        self.assertEqual({d.action for d in decisions[1:]}, {"HOLD"})

    def test_votes_move_the_share_and_the_kill_switch_blocks_raising_it(self):

        self.run_trader(ExposureSpec("vote", ("close>sma20",), core=0.0))
        actions = [d.action for d in reversed(self.store.decisions())]
        self.assertEqual(actions[:19], ["WAIT"] * 19)  # SMA 20 warming up
        self.assertIn("BUY", actions)

        self.store.reset_account()
        self.kill_switch.write_text("stop")
        self.run_trader(ExposureSpec("vote", ("close>sma20",), core=0.0))
        actions = {d.action for d in self.store.decisions()}
        self.assertIn("SKIP", actions)
        self.assertNotIn("BUY", actions)


if __name__ == "__main__":
    unittest.main()
