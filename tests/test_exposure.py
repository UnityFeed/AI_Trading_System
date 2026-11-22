import math
import unittest
from datetime import date, datetime, timedelta, timezone

from src.analysis.technical_indicators import IndicatorRow
from src.backtesting import features
from src.backtesting.engine import CostSettings, run_backtest
from src.backtesting.exposure import (
    ExposureSpec, MissingExternalData, fixed_mix, hash_stress_by_day, mvrv_cap, mvrv_z_by_day,
    plan, run_exposure_backtest,
)
from src.backtesting.market import Market
from src.data_collection.market_data import MarketData


START = datetime(2024, 1, 1, tzinfo=timezone.utc)
NO_COSTS = CostSettings(fee_pct=0.0, slippage_pct=0.0)


def daily_market(closes, gaps=(), opens=None, tradeable=None, external=None) -> Market:
    """Daily candles; `gaps`: day offsets left out. Open = previous close unless given."""
    candles, rows = [], []
    previous = None
    for offset, close in enumerate(closes):
        if offset in gaps:
            previous = None
            continue
        when = START + timedelta(days=offset)
        open_ = opens[offset] if opens else (previous if previous is not None else close)
        candles.append(MarketData("BTC/USD", "crypto", when, open_, max(open_, close), min(open_, close),
                                  close, 1.0, "primary"))
        rows.append(IndicatorRow("primary", "BTC/USD", "1d", when, close, {}))
        previous = close
    consecutive = [False] + [
        b.timestamp - a.timestamp == timedelta(days=1) for a, b in zip(candles, candles[1:])
    ]
    return Market("1d", candles, rows, tradeable or [True] * len(candles), consecutive, external or {})


class TestFeatures(unittest.TestCase):

    def test_sma_and_return_restart_at_gaps(self):
        market = daily_market([1, 2, 3, 4, 5, 6, 7], gaps={3})

        self.assertEqual(features.sma(market, 3), [None, None, 2.0, None, None, 6.0])
        self.assertEqual(features.ret(market, 2), [None, None, 2.0, None, None, 7 / 5 - 1])

    def test_prior_extremes_exclude_the_current_candle(self):
        market = daily_market([5, 1, 9, 3, 2])

        self.assertEqual(features.prior_high(market, 2), [None, None, 5, 9, 9])
        self.assertEqual(features.prior_low(market, 2), [None, None, 1, 1, 1])

    def test_ewma_volatility_warms_up_and_is_yearly(self):
        closes = [100 * math.exp(0.01 * (1 if i % 2 else -1) * (i > 0)) for i in range(40)]
        market = daily_market(closes)

        vol = features.ewma_vol(market, warmup=30)

        self.assertIsNone(vol[29])
        self.assertIsNotNone(vol[30])
        # Every log return is +-0.02 or +-0.01 here: daily std between them, times sqrt(365).
        self.assertTrue(0.01 * math.sqrt(365) < vol[-1] < 0.021 * math.sqrt(365))


class TestPlan(unittest.TestCase):

    def test_votes_core_and_warm_up(self):
        closes = [10] * 25 + [20] * 5
        market = daily_market(closes)

        targets = plan(market, ExposureSpec("t", ("close>sma20",), core=0.5)).targets

        self.assertIsNone(targets[18])  # SMA 20 not warmed up
        self.assertEqual(targets[24], 0.5)  # close equals the average: vote no, core only
        self.assertEqual(targets[25], 1.0)

    def test_fixed_weight_and_volatility_cap(self):
        market = daily_market([100 * (1.05 if i % 2 else 1.0) for i in range(60)])

        self.assertEqual(plan(market, ExposureSpec("f", fixed_weight=0.6)).targets, [0.6] * 60)

        capped = plan(market, ExposureSpec("v", fixed_weight=1.0, vol_target_pct=10)).targets
        self.assertIsNone(capped[0])
        self.assertTrue(all(t is None or t < 1.0 for t in capped))
        self.assertIsNotNone(capped[-1])

    def test_external_data_is_required_and_lagged(self):
        market = daily_market([100.0] * 10)
        with self.assertRaises(MissingExternalData):
            plan(market, ExposureSpec("m", fixed_weight=1.0, mvrv_cap=True))

        # MVRV-Z jumps to a very high level on 5 Jan: with a 1-day delay (after
        # the day itself is complete), the first candle to see it closes 7 Jan.
        days = [date(2023, 1, 1) + timedelta(days=k) for k in range(500)]
        caps = {d: 1e12 for d in days}
        ratio = {d: (1.0001 if d < date(2024, 1, 5) else 100.0) for d in days}
        caps.update({d: 1e12 * (1 + k % 3 / 100) for k, d in enumerate(days) if d < date(2024, 1, 5)})
        market = daily_market([100.0] * 10, external={"mvrv": ratio, "market_cap_usd": caps})

        targets = plan(market, ExposureSpec("m", fixed_weight=1.0, mvrv_cap=True)).targets

        self.assertEqual(targets[4], 1.0)   # candle of 5 Jan closes 6 Jan: knows up to 4 Jan
        self.assertEqual(targets[5], 0.25)  # candle of 6 Jan closes 7 Jan: knows 5 Jan

    def test_hash_filter_blocks_increases_only(self):
        days = [date(2023, 10, 1) + timedelta(days=k) for k in range(120)]
        # Falling hash rate: 30-day average below the 60-day average (stress).
        falling = {d: 1000.0 - k for k, d in enumerate(days)}
        closes = [10] * 25 + [20] * 5
        market = daily_market(closes, external={"hash_rate": falling})

        targets = plan(market, ExposureSpec("h", ("close>sma20",), hash_filter=True)).targets

        self.assertEqual(targets[24], 0.0)
        self.assertEqual(targets[25], 0.0)  # the vote says buy, the filter blocks it

    def test_mvrv_z_uses_only_the_past_and_buckets(self):
        days = [date(2020, 1, 1) + timedelta(days=k) for k in range(40)]
        caps = {d: 100.0 + k for k, d in enumerate(days)}
        ratios = {d: 2.0 for d in days}
        z = mvrv_z_by_day(ratios, caps)
        self.assertNotIn(days[28], z)
        self.assertIn(days[29], z)
        # Adding later days must not change an earlier value.
        caps2 = {**caps, date(2020, 3, 1): 1e9}
        ratios2 = {**ratios, date(2020, 3, 1): 2.0}
        self.assertEqual(mvrv_z_by_day(ratios2, caps2)[days[35]], z[days[35]])
        self.assertEqual([mvrv_cap(v) for v in (2.9, 3, 4.9, 5)], [1.0, 0.5, 0.5, 0.25])

    def test_hash_stress_needs_60_consecutive_days(self):
        days = [date(2020, 1, 1) + timedelta(days=k) for k in range(61)]
        rising = {d: float(k) for k, d in enumerate(days)}
        stress = hash_stress_by_day(rising)
        self.assertEqual(sorted(stress), days[59:])
        self.assertEqual(stress[days[60]], 0.0)


class TestExposureBacktest(unittest.TestCase):

    def test_full_in_and_out_matches_the_rules_engine(self):
        closes = [100, 110, 120, 90, 95, 130, 125]
        market = daily_market(closes)
        entry = [False, True, False, False, True, False, False]
        exit_signal = [False, False, True, False, False, False, False]
        targets = [None, 1.0, 0.0, None, 1.0, None, None]
        costs = CostSettings(fee_pct=0.8, slippage_pct=0.05)

        rules = run_backtest(market, range(len(closes)), entry, exit_signal, None, costs)
        graded = run_exposure_backtest(market, range(len(closes)), targets, 0.125, costs)

        self.assertAlmostEqual(graded.final_equity, rules.final_equity, places=12)
        self.assertEqual(len(graded.rebalances), 3)
        self.assertAlmostEqual(graded.turnover, 3.0, delta=0.2)

    def test_band_and_partial_fees(self):
        market = daily_market([100.0] * 6)
        costs = CostSettings(fee_pct=1.0, slippage_pct=0.0)
        # 0.5 -> 0.6 is below a band of 0.125: no trade; 0.5 -> 0.0 is traded.
        targets = [0.5, 0.6, 0.6, 0.0, None, None]

        result = run_exposure_backtest(market, range(6), targets, 0.125, costs)

        self.assertEqual([round(r.to_weight, 3) for r in result.rebalances], [0.497, 0.0])
        # Fee 1% on 0.5 bought, then 1% on the ~0.495 sold.
        self.assertAlmostEqual(result.final_equity, 1 - 0.005 - 0.495 * 0.01, places=4)
        self.assertEqual(result.end_weight, 0.0)

    def test_orders_wait_for_a_tradeable_open_and_report_pending(self):
        market = daily_market([100.0, 100.0, 120.0, 130.0], tradeable=[True, True, False, True])

        result = run_exposure_backtest(market, range(4), [None, 1.0, None, 0.0], 0.125, NO_COSTS)

        self.assertEqual(result.rebalances[0].time, START + timedelta(days=3))  # day 2 not tradeable
        self.assertEqual(result.pending_target, 0.0)  # decided at the last close
        self.assertAlmostEqual(result.final_equity, 130 / 120)

    def test_exposure_is_the_average_share(self):
        market = daily_market([100.0] * 5)
        held = fixed_mix(market, range(5), 0.5, NO_COSTS)
        self.assertAlmostEqual(held.exposure_pct, 40.0)  # 0% on day 1, 50% after
        self.assertAlmostEqual(held.final_equity, 1.0)


if __name__ == "__main__":
    unittest.main()
