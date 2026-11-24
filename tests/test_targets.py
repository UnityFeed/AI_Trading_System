"""Price targets: real chart levels, merged and ordered, with chances that use only the past."""

import math
import unittest

import numpy as np

from src.predictive_engine import targets
from src.predictive_engine.outcomes import candle_volatility
from tests.test_predictive_tools import market, walk


class TestLevels(unittest.TestCase):

    def test_nearest_three_per_side_merged_with_their_reasons(self):
        tools = {
            "zones": [{"low": 101.0, "high": 102.0, "touches": 3}, {"low": 95.0, "high": 96.0, "touches": 2}],
            "fibonacci": {"levels": [{"name": "1.618", "price": 101.2}, {"name": "0.5", "price": 90.0},
                                     {"name": "1.272", "price": 120.0}, {"name": "2.618", "price": 140.0}]},
            "patterns": [{"status": "confirmed", "target": 110.0, "kind": "double bottom"},
                         {"status": "hit", "target": 130.0, "kind": "old"}],
        }
        out = targets.candidate_levels(100.0, tools, swing_high=105.0, swing_low=None)
        up = [t for t in out if t["side"] == "up"]
        down = [t for t in out if t["side"] == "down"]
        self.assertEqual([t["price"] for t in up], [101.0, 105.0, 110.0])  # 101.2 merged into 101
        self.assertEqual(up[0]["why"], ["resistance zone (3 turns)", "Fibonacci 1.618"])
        self.assertEqual([t["name"] for t in up], ["T1", "T2", "T3"])
        self.assertEqual([t["price"] for t in down], [96.0, 90.0])  # nearest first
        self.assertTrue(all(t["distance_pct"] < 0 for t in down))


class TestChances(unittest.TestCase):

    def test_chance_uses_only_windows_that_ended_and_is_a_fraction(self):
        c = walk(800)
        m = market(c)
        vol = candle_volatility(m)
        exc = targets.excursions(c, m.consecutive, vol, 7)
        ai = np.full(len(c), 0.3)
        i = 600
        chance, cases = targets.touch_chance(i, 0.5, "up", exc, ai)
        self.assertTrue(0 <= chance <= 1)
        known = np.flatnonzero(exc.known_at <= i)
        self.assertEqual(cases, int((~np.isnan(exc.up[known])).sum()))
        # changing the future (after candle i) must not change the chance
        exc2 = targets.Excursions(exc.up.copy(), exc.down.copy(), exc.known_at.copy())
        exc2.up[i - 6:] = 99.0
        self.assertEqual(targets.touch_chance(i, 0.5, "up", exc2, ai), (chance, cases))

    def test_further_levels_are_less_likely(self):
        c = walk(900)
        m = market(c)
        exc = targets.excursions(c, m.consecutive, candle_volatility(m), 14)
        ai = np.full(len(c), math.nan)
        near, _ = targets.touch_chance(850, 0.3, "up", exc, ai)
        far, _ = targets.touch_chance(850, 1.5, "up", exc, ai)
        self.assertGreater(near, far)


if __name__ == "__main__":
    unittest.main()
