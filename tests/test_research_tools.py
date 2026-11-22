import random
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.backtesting.engine import BacktestResult, CostSettings
from src.backtesting.ledger import daily_sharpes, log_trials, read_trials, trial_count
from src.backtesting.metrics import break_even_fee, daily_returns, sharpe, sortino, top_days_capture
from src.backtesting.validation import (
    deflated_sharpe, expected_max_sharpe, probability_of_overfitting,
)
from src.data_collection.external_data import ExternalDataStore, update_external_data
from src.data_collection.kraken_trades_provider import KrakenTradesProvider
from src.data_collection.order_flow import (
    OrderFlowStore, aggregate_trade_flow, collect_trade_flow, record_book, summarise_book,
)


DAY0 = datetime(2024, 1, 1, tzinfo=timezone.utc)


def result_from(values, start=DAY0) -> BacktestResult:
    curve = [(start + timedelta(days=i), v) for i, v in enumerate(values)]
    return BacktestResult(curve[0][0], curve[-1][0], values[-1], 0.0, 100.0, equity_curve=curve)


class TestMetrics(unittest.TestCase):

    def test_daily_returns_use_the_last_value_of_each_day(self):
        curve = [(DAY0, 1.0), (DAY0 + timedelta(hours=23), 2.0), (DAY0 + timedelta(days=1), 3.0)]
        self.assertEqual(daily_returns(curve), [(DAY0 + timedelta(days=1), 0.5)])

    def test_sharpe_and_sortino(self):
        self.assertEqual(sharpe([0.01] * 10), 0.0)  # no swings: undefined, reported as 0
        returns = [0.02, -0.01] * 50
        self.assertGreater(sharpe(returns), 0)
        self.assertGreater(sortino(returns), sharpe(returns))  # only falling days count

    def test_top_days_capture(self):
        held = result_from([1, 1.1, 1.0, 1.3, 1.2])       # best days: +30%, +10%
        half = result_from([1, 1.05, 1.0, 1.15, 1.1])     # half in BTC on those days
        cash = result_from([1, 1, 1, 1, 1])
        self.assertAlmostEqual(top_days_capture(held, held, n=2), 1.0)
        self.assertAlmostEqual(top_days_capture(cash, held, n=2), 0.0)
        self.assertAlmostEqual(top_days_capture(half, held, n=2), (0.05 + 0.15) / (0.1 + 0.3), places=6)

    def test_break_even_fee(self):
        hold = lambda c: BacktestResult(DAY0, DAY0, 2.0 * (1 - c.fee_pct / 100) ** 2, 0, 100)
        # 10 round trips: wins without fees, loses at high fees.
        trader = lambda c: BacktestResult(DAY0, DAY0, 2.2 * (1 - c.fee_pct / 100) ** 20, 0, 100)
        fee = break_even_fee(trader, hold, 0.05)
        self.assertTrue(0.4 < fee < 0.6)
        never = lambda c: BacktestResult(DAY0, DAY0, 1.5, 0, 100)
        self.assertIsNone(break_even_fee(never, hold, 0.05))


class TestValidation(unittest.TestCase):

    def test_deflated_sharpe_falls_with_more_trials(self):
        rng = random.Random(1)
        returns = [rng.gauss(0.002, 0.02) for _ in range(1500)]
        one = deflated_sharpe(returns, 1, 0.0)
        many = deflated_sharpe(returns, 1000, 0.002)
        self.assertGreater(one, 0.95)
        self.assertLess(many, one)
        self.assertEqual(expected_max_sharpe(1, 0.1), 0.0)
        self.assertGreater(expected_max_sharpe(100, 0.01), expected_max_sharpe(10, 0.01))

    def test_pbo_noise_vs_a_real_edge(self):
        # Pure noise: on average the "best" lands in the bottom half half the time
        # (one sample varies a lot, so average a few).
        values = []
        for seed in range(6):
            rng = random.Random(seed)
            noise = [[rng.gauss(0, 0.01) for _ in range(10)] for _ in range(1000)]
            values.append(probability_of_overfitting(noise, blocks=10))
        self.assertTrue(0.3 < sum(values) / len(values) < 0.7)

        rng = random.Random(7)

        edge = [[rng.gauss(0.003 if j == 0 else 0.0, 0.01) for j in range(6)] for _ in range(800)]
        self.assertLess(probability_of_overfitting(edge, blocks=8), 0.1)
        self.assertIsNone(probability_of_overfitting([[0.1]] * 200))


class TestLedger(unittest.TestCase):

    def test_append_read_and_count(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sub" / "trials.csv"
            log_trials([{"script": "a", "strategy": "x", "daily_sharpe": 0.05}], path)
            log_trials([{"script": "b", "n_trials": 540, "unknown_field": 1}], path)
            rows = read_trials(path)
            self.assertEqual(len(rows), 2)
            self.assertEqual(trial_count(rows), 541)
            self.assertEqual(daily_sharpes(rows), [0.05])
            self.assertEqual(read_trials(Path(folder) / "missing.csv"), [])


class TestExternalData(unittest.TestCase):

    def test_first_value_is_kept_and_revisions_logged(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ExternalDataStore(Path(folder) / "ext.db")
            d1, d2 = date(2024, 1, 1), date(2024, 1, 2)
            self.assertEqual(store.save("mvrv", {d1: 1.5}), (1, 0))
            self.assertEqual(store.save("mvrv", {d1: 1.6, d2: 1.7}), (1, 1))
            self.assertEqual(store.load("mvrv"), {d1: 1.5, d2: 1.7})
            self.assertEqual(store.latest_day("mvrv"), d2)

            asked = []

            def fake_fetch(start):
                asked.append(start)
                return {"mvrv": {date(2024, 1, 3): 1.8}, "market_cap_usd": {}, "hash_rate": {}}

            update_external_data(store, log=lambda *a: None, fetch=fake_fetch)
            self.assertIsNone(asked[0])  # not every series has data yet: full history
            self.assertEqual(store.latest_day("mvrv"), date(2024, 1, 3))


class TestOrderFlow(unittest.TestCase):

    def test_aggregate_hourly_buy_sell_and_vwap(self):
        t = DAY0 + timedelta(minutes=5)
        flows = aggregate_trade_flow([
            (t, 100.0, 1.0, "b"), (t, 110.0, 3.0, "s"), (t + timedelta(hours=1), 120.0, 2.0, "b"),
        ])
        self.assertEqual(len(flows), 2)
        self.assertEqual((flows[0].buy_volume, flows[0].sell_volume, flows[0].delta), (1.0, 3.0, -2.0))
        self.assertAlmostEqual(flows[0].vwap, (100 + 330) / 4)
        self.assertEqual(flows[0].hour, DAY0)

    def test_book_summary(self):
        bids = [(99.9, 1.0), (99.6, 2.0), (98.0, 5.0)]
        asks = [(100.1, 1.0), (100.4, 4.0), (102.0, 5.0)]
        s = summarise_book(bids, asks)
        self.assertAlmostEqual(s["spread_pct"], 0.2)
        self.assertEqual((s["bid_depth_05"], s["ask_depth_05"]), (3.0, 5.0))
        self.assertAlmostEqual(s["imbalance_05"], -0.25)

    def test_store_and_forward_collection(self):
        class FakeProvider:
            calls = []

            def fetch_trades_with_side(self, start, end):
                self.calls.append((start, end))
                return [(start + timedelta(minutes=1), 100.0, 1.0, "b")]

        with tempfile.TemporaryDirectory() as folder:
            store = OrderFlowStore(Path(folder) / "flow.db")
            now = DAY0 + timedelta(days=2, minutes=30)
            provider = FakeProvider()
            self.assertEqual(collect_trade_flow(store, provider, now, timedelta(hours=3), log=lambda *a: None), 1)
            self.assertEqual(provider.calls[0], (DAY0 + timedelta(hours=45), DAY0 + timedelta(hours=48)))
            # Next call starts after the stored hour, and never includes the running hour.
            collect_trade_flow(store, provider, now, log=lambda *a: None)
            self.assertEqual(provider.calls[1], (DAY0 + timedelta(hours=46), DAY0 + timedelta(hours=48)))
            self.assertEqual(collect_trade_flow(store, provider, DAY0 + timedelta(hours=47, minutes=5),
                                                log=lambda *a: None), 0)

            record_book(store, DAY0, fetch=lambda: ([(99.0, 1.0)], [(101.0, 1.0)]))
            self.assertEqual(store.book_count(), 1)


class TestTradesWithSide(unittest.TestCase):

    @patch("src.data_collection.kraken_trades_provider.urlopen")
    def test_side_is_kept(self, mock_urlopen):
        start = DAY0
        t = start.timestamp()
        page = (b'{"error":[],"result":{"XXBTZUSD":[["100.0","0.5",%f,"b","m","",1],'
                b'["101.0","0.25",%f,"s","l","",2]],"last":"%d"}}'
                % (t + 10, t + 4000, int((t + 4000) * 1e9)))
        def respond(*args, **kwargs):
            response = MagicMock()
            response.__enter__.return_value = BytesIO(page)
            return response

        mock_urlopen.side_effect = respond

        trades = KrakenTradesProvider().fetch_trades_with_side(start, start + timedelta(hours=1))
        self.assertEqual([(p, v, s) for _, p, v, s in trades], [(100.0, 0.5, "b")])
        plain = KrakenTradesProvider().fetch_trades(start, start + timedelta(hours=1))
        self.assertEqual(len(plain[0]), 3)


if __name__ == "__main__":
    unittest.main()
