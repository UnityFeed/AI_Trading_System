import math
import random
import unittest
from datetime import date, datetime, timedelta, timezone

from src.analysis.technical_indicators import calculate_indicators
from src.analysis.timeframes import aggregate_hourly_candles, period_start
from src.backtesting.engine import CostSettings
from src.backtesting.market import Market
from src.backtesting.report import strategy_report, strategy_state
from src.data_collection.market_data import MarketData
from src.research import lab, models
from src.research.features import build_frame, coinbase_premium, expanding_rank, weekly_from_daily
from src.research.turning_points import event_study, lag_study, zigzag
from src.strategies.registry import get_strategy
from tests.helpers import hourly_candles


START = datetime(2020, 1, 6, tzinfo=timezone.utc)  # a Monday


def daily_market(days: int = 900, seed: int = 3, external=None) -> Market:
    rng = random.Random(seed)
    price = 100.0
    candles = []
    for k in range(days):
        open_ = price
        price *= math.exp(rng.gauss(0.001, 0.03) + 0.2 * math.sin(k / 60) / 60)
        high, low = max(open_, price) * 1.01, min(open_, price) * 0.99
        candles.append(MarketData("BTC/USD", "crypto", START + timedelta(days=k), open_, high, low, price,
                                  1000 + 200 * rng.random(), "primary"))
    rows = calculate_indicators(candles, "1d")
    consecutive = [False] + [True] * (days - 1)
    return Market("1d", candles, rows, [True] * days, consecutive, external or {})


def truncated(market: Market, n: int) -> Market:
    return Market("1d", market.candles[:n], market.rows[:n], market.tradeable[:n], market.consecutive[:n],
                  market.external)


class TestWeekly(unittest.TestCase):

    def test_weeks_start_on_monday_and_need_every_hour(self):
        self.assertEqual(period_start(datetime(2026, 11, 22, 15, tzinfo=timezone.utc), "1w"),
                         datetime(2026, 11, 16, tzinfo=timezone.utc))
        hours = hourly_candles([100.0] * (24 * 15), start=START)
        weeks = aggregate_hourly_candles(hours, "1w")
        self.assertEqual([c.timestamp for c in weeks.candles], [START, START + timedelta(days=7)])
        self.assertEqual(len(weeks.incomplete_periods), 1)  # the third week has only one day

    def test_weekly_from_daily_skips_incomplete_weeks(self):
        market = daily_market(20)
        weeks = weekly_from_daily(market.candles)
        self.assertEqual(len(weeks), 2)
        self.assertEqual(weeks[0].close, market.candles[6].close)


class TestFeatures(unittest.TestCase):

    def test_ranks_use_only_the_past(self):
        self.assertEqual(expanding_rank([3.0, 1.0, 2.0, 5.0], min_history=2), [None, None, 0.5, 1.0])

    def test_no_feature_looks_ahead(self):
        """Every feature on a shortened history equals the same feature on the full history."""
        full = daily_market(900)
        short_n = 700
        a = build_frame(full)
        b = build_frame(truncated(full, short_n))
        for name in a.values:
            with self.subTest(feature=name):
                self.assertEqual(a.values[name][:short_n], b.values[name])
                self.assertEqual(a.ranks[name][:short_n], b.ranks[name])

    def test_weekly_values_appear_only_after_the_week_ends(self):
        frame = build_frame(daily_market(400))
        values = frame.values["weekly.ret_4w"]
        # START is a Monday: day 6 (Sunday) closes the first week; the Saturday before must not see it
        changes = [i for i in range(1, 400) if values[i] != values[i - 1]]
        self.assertTrue(changes)
        self.assertTrue(all(i % 7 == 6 for i in changes))

    def test_coinbase_premium(self):
        hours = hourly_candles([100.0] * 24, start=START)
        coinbase = hourly_candles([101.0] * 24, start=START, exchange="coinbase")
        premium = coinbase_premium(hours, coinbase)
        self.assertAlmostEqual(premium[START.date()], 0.01)
        self.assertEqual(coinbase_premium(hours[:5], coinbase), {})  # too few hours


class TestTurningPoints(unittest.TestCase):

    def test_lag_and_event_study(self):
        closes = [100, 120, 80, 70, 90, 110, 95]
        times = [START + timedelta(days=i) for i in range(len(closes))]
        turns = zigzag(closes, times, 0.2)
        self.assertEqual([(t.kind, t.price) for t in turns], [("low", 100), ("high", 120), ("low", 70)])
        rows = lag_study(turns, [("buy", times[5], 110.0), ("sell", times[4], 90.0)])
        buy = next(r for r in rows if r.side == "buy")
        self.assertEqual(buy.days_late, 2.0)
        self.assertAlmostEqual(buy.pct_missed, (110 / 70 - 1) * 100, places=1)

        frame = build_frame(daily_market(900))
        market = frame.market
        evidence = event_study(frame, zigzag([c.close for c in market.candles],
                                             [c.timestamp for c in market.candles], 0.15))
        self.assertTrue(evidence)
        self.assertTrue(all(e.rank_all_days is None or 0 <= e.rank_all_days <= 1 for e in evidence))


class TestLab(unittest.TestCase):

    def test_state_machine(self):
        flags = {"f": [True, True, True, False, True, True], "none": [True] * 6}
        triggers = {"t": [False, True, False, False, True, False]}
        exits = {"filter_off": None, "never (only trail/filter)": [False] * 6}
        closes = [10, 10, 12, 12, 10, 7]
        spec = lab.LabSpec("f", "t", "filter_off", None, 0.0)
        self.assertEqual(lab.holding_state(spec, closes, flags, triggers, exits), [0, 1, 1, 0, 1, 1])
        trail = lab.LabSpec("none", "t", "never (only trail/filter)", 0.2, 0.5)
        state = lab.holding_state(trail, closes, flags, triggers, exits)
        self.assertEqual(state, [0, 1, 1, 1, 1, 0])  # peak 12: 10 is -17% (kept), 7 is -42% (sold)
        self.assertEqual(lab.targets_for(trail, state)[:2], [0.5, 1.0])

    def test_vote_names_round_trip(self):
        spec = lab.parse_vote("lab:weekly macd>signal|momentum 28d strong (rank>0.8)|close crosses below sma200|")
        self.assertEqual((spec.filter, spec.trail), ("weekly macd>signal", None))
        self.assertEqual(lab.parse_vote("lab:a|b|c|0.2").trail, 0.2)

    def test_search_and_walk_forward(self):
        market = daily_market(900)
        frame = build_frame(market)
        blocks = lab.building_blocks(frame)
        specs = lab.all_specs(blocks)[:40]
        hold = lab.hold_benchmark(market, CostSettings())
        lab._init(market, blocks, hold.years, hold.daily, CostSettings())
        results = [r for r in (lab.evaluate(s) for s in specs) if r is not None]
        self.assertTrue(results)
        r = results[0]
        self.assertEqual(set(r.years), set(hold.years))
        for method in ("single", "family", "top10"):
            rows = lab.walk_forward(results, method, first_year=2022)
            self.assertTrue(all(row.year >= 2022 for row in rows))

    def test_registered_lab_strategy_runs_in_the_app_engine(self):
        market = daily_market(900)
        definition = get_strategy("lab-weekly-momentum-core50-1d")
        report = strategy_report(market, definition, CostSettings())
        self.assertEqual(report["kind"], "exposure")
        state = strategy_state(market, definition)
        roles = [r["role"] for r in state["rules"]]
        self.assertIn("Filter", roles)
        self.assertIn("Holding (overlay)", roles)


class TestModels(unittest.TestCase):

    def test_logistic_learns_a_clear_pattern(self):
        rng = random.Random(1)
        rows = [[rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5)] for _ in range(400)]
        ys = [int(x[0] > 0) for x in rows]
        w = models.fit_logistic(rows, ys, iterations=300, rate=2.0)
        self.assertGreater(models.predict_logistic(w, [0.4, 0.0]), 0.7)
        self.assertLess(models.predict_logistic(w, [-0.4, 0.0]), 0.3)

    def test_low_labels_only_use_confirmed_lows(self):
        frame = build_frame(daily_market(600))
        closes = [c.close for c in frame.market.candles]
        cutoff = 400
        labels = models.labels_low_known_before(frame, cutoff)
        turns = zigzag(closes[:cutoff], [c.timestamp for c in frame.market.candles][:cutoff], 0.2)
        last = turns[-1].index if turns else 0
        self.assertTrue(all(v is None for v in labels[last + 1:]))

    def test_scores(self):
        preds = [models.Prediction(i, START, 0.9 if i % 2 else 0.1, i % 2) for i in range(100)]
        s = models.score(preds, 0.5)
        self.assertGreater(s.skill, 0.5)
        self.assertEqual(sum(n for _, _, n in s.calibration), 100)
        exposure = models.exposure_from_probability(preds[:4], 5, 0.45, 0.55, core=0.5)
        self.assertEqual(exposure, [0.5, 1.0, 0.5, 1.0, None])


if __name__ == "__main__":
    unittest.main()
