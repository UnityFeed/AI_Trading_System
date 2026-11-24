import math
import random
import unittest
from datetime import datetime, timedelta, timezone

from src.analysis.technical_indicators import calculate_indicators
from src.backtesting.market import Market
from src.data_collection.market_data import MarketData
from src.predictive_engine import learner
from src.predictive_engine.levels import adx, fibonacci, support_resistance
from src.predictive_engine.patterns import detect_patterns, status_at
from src.predictive_engine.service import EngineService
from src.predictive_engine.structure import Pivot
from src.predictive_engine.volume_profile import volume_profile
from tests.helpers import hourly_candles


START = datetime(2015, 1, 5, tzinfo=timezone.utc)


def candles(closes):
    out, prev = [], closes[0]
    for k, c in enumerate(closes):
        out.append(MarketData("BTC/USD", "crypto", START + timedelta(days=k), prev, max(prev, c) * 1.005,
                              min(prev, c) * 0.995, c, 1000.0, "primary"))
        prev = c
    return out


def walk(n=900, seed=3):
    rng = random.Random(seed)
    price, closes = 100.0, []
    for _ in range(n):
        price *= math.exp(rng.gauss(0.0008, 0.03))
        closes.append(price)
    return candles(closes)


def market(c):
    return Market("1d", c, calculate_indicators(c, "1d"), [True] * len(c), [False] + [True] * (len(c) - 1))


def pivot(i, price, kind, confirmed=None):
    t = START + timedelta(days=i)
    return Pivot(i, t, price, kind, confirmed if confirmed is not None else i + 3, t)


class TestLevels(unittest.TestCase):

    def test_zones_merge_nearby_turns_and_only_use_confirmed_swings(self):
        pivots = [pivot(1, 100, "low"), pivot(5, 120, "high"), pivot(9, 101, "low"), pivot(14, 119.5, "high"),
                  pivot(20, 100.5, "low", confirmed=40)]
        zones = support_resistance(pivots, 110, at_index=30)
        support = next(z for z in zones if z.kind == "support")
        self.assertEqual(support.touches, 2)  # the third low is not confirmed yet at candle 30
        self.assertEqual(next(z for z in zones if z.kind == "resistance").touches, 2)

    def test_fibonacci_of_the_last_swing(self):
        f = fibonacci([pivot(1, 100, "low"), pivot(5, 200, "high")], at_index=10)
        self.assertEqual(f.direction, "up")
        self.assertAlmostEqual(f.retracements[0.5], 150)
        self.assertAlmostEqual(f.extensions[1.618], 261.8)
        self.assertIsNone(fibonacci([pivot(1, 100, "low")], at_index=10))

    def test_adx_strong_in_a_steady_trend(self):
        values = adx(candles([100 * 1.01 ** k for k in range(80)]))
        self.assertIsNone(values[10])
        self.assertGreater(values[-1], 40)

    def test_volume_profile(self):
        hours = hourly_candles([100.0] * 20 + [110.0] * 5)
        vp = volume_profile(hours, bins=10)
        self.assertLess(abs(vp.poc - 100), 2)
        self.assertLessEqual(vp.val, vp.poc)
        self.assertGreaterEqual(vp.vah, vp.poc)


class TestPatterns(unittest.TestCase):

    def test_double_bottom_life_cycle(self):
        closes = [100, 95, 90, 85, 80, 84, 88, 92, 95, 91, 86, 81, 80.5, 84, 88, 92, 96, 99, 103, 108, 112, 116, 118, 117]
        found = [p for p in detect_patterns(candles(closes), "1d", left=2, right=2) if p.kind == "double bottom"]
        self.assertTrue(found)
        p = found[0]
        self.assertEqual(status_at(p, p.detected_index - 1), None)
        self.assertEqual(status_at(p, p.detected_index), "candidate")
        self.assertIn(p.status, ("hit", "confirmed"))
        self.assertGreater(p.target, p.breakout_price)

    def test_no_look_ahead(self):
        """A pattern's history up to a cut is the same on the shortened chart."""
        c = walk(700)
        full = detect_patterns(c, "1d")
        cut = 500
        part = detect_patterns(c[:cut], "1d")
        def known(patterns):
            return sorted((p.kind, p.detected_index, tuple((i, s) for i, s in p.history if i < cut))
                          for p in patterns if p.detected_index < cut)
        self.assertEqual(known(full), known(part))


class TestLearner(unittest.TestCase):

    def test_replay_forecasts_add_up_and_never_see_the_future(self):
        c = walk(900)
        m = market(c)
        names, rows, keys = learner.build_inputs(m)
        full = learner.replay(m, 14, names, rows, keys)
        cut = 700
        m2 = market(c[:cut])
        names2, rows2, keys2 = learner.build_inputs(m2)
        part = learner.replay(m2, 14, names2, rows2, keys2)
        checked = 0
        for i in range(cut):
            if full.forecasts[i] is None:
                self.assertIsNone(part.forecasts[i])
                continue
            checked += 1
            self.assertAlmostEqual(sum(full.forecasts[i].values()), 1.0, places=9)
            for k in learner.KINDS:
                self.assertAlmostEqual(full.forecasts[i][k], part.forecasts[i][k], places=9)
        self.assertGreater(checked, 300)

    def test_service_replay_day_and_tools(self):
        c = walk(900)
        hours = []
        for d in c[-120:]:
            hours += [MarketData("BTC/USD", "crypto", d.timestamp + timedelta(hours=h), d.open, d.high, d.low,
                                 d.close, 10.0, "primary") for h in range(24)]
        svc = EngineService(market(c), hours)
        now = svc.scenarios(7)
        past = svc.scenarios(7, c[600].timestamp)
        self.assertEqual(past["candle_time"], c[600].timestamp.isoformat())
        self.assertIsNotNone(past["outcome"])
        self.assertTrue(set(learner.EXPERTS) <= set(now["weights"]))
        tools = svc.tools("1d", c, c[600].timestamp)
        self.assertEqual(tools["time"], int(c[600].timestamp.timestamp()))
        self.assertTrue(all(p["status"] for p in tools["patterns"]))


if __name__ == "__main__":
    unittest.main()
