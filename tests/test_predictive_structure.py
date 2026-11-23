import math
import random
import unittest
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from src.data_collection.market_data import MarketData
from src.predictive_engine.structure import analyse, raw_pivots


START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def candles_from(closes, gaps=()):
    out = []
    for k, close in enumerate(closes):
        if k in gaps:
            continue
        out.append(MarketData("BTC/USD", "crypto", START + timedelta(days=k), close, close + 1, close - 1,
                              close, 1.0, "primary"))
    return out


def random_walk(n=600, seed=5):
    rng = random.Random(seed)
    price, closes = 100.0, []
    for _ in range(n):
        price *= math.exp(rng.gauss(0, 0.03))
        closes.append(price)
    return candles_from(closes)


class TestPivots(unittest.TestCase):

    def test_pivot_is_known_only_after_the_right_candles(self):
        closes = [10, 11, 12, 15, 12, 11, 10, 9]
        pivots = raw_pivots(candles_from(closes), "1d", left=2, right=2)
        high = next(p for p in pivots if p.kind == "high")
        self.assertEqual((high.index, high.confirmed_index), (3, 5))
        self.assertEqual(high.confirmed_time, START + timedelta(days=6))  # close of candle 5

    def test_no_pivot_across_a_gap(self):
        closes = [10, 11, 12, 15, 12, 11, 10]
        self.assertFalse([p for p in raw_pivots(candles_from(closes, gaps={4}), "1d", 2, 2) if p.kind == "high"])


class TestStructure(unittest.TestCase):

    def test_labels_trend_and_events(self):
        # up-swings making higher highs and higher lows, then a break down
        closes = [10, 12, 14, 20, 16, 14, 13, 15, 18, 25, 21, 19, 18, 20, 22, 26, 30, 24, 15, 12, 10, 9]
        s = analyse(candles_from(closes), "1d", left=2, right=2)
        labels = [(p.kind, p.label) for p in s.pivots]
        self.assertIn(("high", "HH"), labels)
        self.assertIn(("low", "HL"), labels)
        kinds = [(e.kind, e.direction) for e in s.events]
        self.assertIn(("BOS", "up"), kinds)
        self.assertIn(("CHoCH", "down"), kinds)
        self.assertEqual(s.trend[-1], "down")
        self.assertEqual(len(s.trend), len(closes))

    def test_sweep_when_the_close_holds(self):
        candles = candles_from([10, 12, 14, 20, 16, 14, 13, 15, 18, 19])
        # candle 9 pokes above the swing high (21) but closes below it
        last = candles[-1]
        candles[-1] = MarketData(last.symbol, last.market, last.timestamp, 18, 23, 17, 19, 1.0, last.exchange)
        s = analyse(candles, "1d", left=2, right=2)
        self.assertEqual([(e.kind, e.direction) for e in s.events][-1], ("sweep", "up"))

    def test_no_look_ahead(self):
        """Structure on a shortened history equals the same part of the full result."""
        full_candles = random_walk(600)
        full = analyse(full_candles, "1d")
        for cut in (150, 333, 480):
            with self.subTest(cut=cut):
                part = analyse(full_candles[:cut], "1d")
                self.assertEqual(part.trend, full.trend[:cut])
                self.assertEqual(part.swing_high, full.swing_high[:cut])
                self.assertEqual(part.swing_low, full.swing_low[:cut])
                self.assertEqual([asdict(e) for e in part.events],
                                 [asdict(e) for e in full.events if e.index < cut])
                known = [p for p in full.pivots if p.confirmed_index < cut]
                # a swing known by `cut` may later be replaced by a more extreme one of the same kind,
                # so compare only the swings that the full run also kept
                self.assertTrue(all(p in part.pivots or p.confirmed_index >= cut for p in known))

    def test_swings_alternate(self):
        s = analyse(random_walk(400, seed=9), "1d")
        kinds = [p.kind for p in s.pivots]
        self.assertTrue(all(a != b for a, b in zip(kinds, kinds[1:])))


if __name__ == "__main__":
    unittest.main()


class TestOutcomes(unittest.TestCase):

    def market(self, closes):
        from src.analysis.technical_indicators import calculate_indicators
        from src.backtesting.market import Market
        candles = candles_from(closes)
        return Market("1d", candles, calculate_indicators(candles, "1d"), [True] * len(candles),
                      [False] + [True] * (len(candles) - 1))

    def test_first_barrier_wins_and_the_end_is_unknown(self):
        from src.predictive_engine.outcomes import BaseRates, outcomes
        flat = [100.0 + (i % 2) for i in range(40)]  # calm: barrier at the 3% floor
        closes = flat + [100, 101, 104, 90, 100, 100, 100, 100, 100, 100]
        out = outcomes(self.market(closes), horizon=5, k=1.0, min_move=0.03)
        first = out[40]
        self.assertEqual((first.kind, first.days), ("bull", 2))  # 104 >= 103 before the drop to 90
        self.assertEqual(out[42].kind, "bear")  # from 104: 90 is below 100.88
        self.assertEqual(out[44].kind, "range")
        self.assertTrue(all(o is None for o in out[-5:]))  # not decided yet
        rates = BaseRates.of([o for o in out if o is not None])
        self.assertAlmostEqual(rates.bull + rates.bear + rates.range, 1.0)

    def test_no_look_ahead_in_known_outcomes(self):
        """An outcome decided before the cut is the same on the shortened history."""
        from src.predictive_engine.outcomes import outcomes
        closes = [c.close for c in random_walk(500)]
        full = outcomes(self.market(closes))
        part = outcomes(self.market(closes[:400]))
        for a, b in zip(full[:400], part):
            if a is not None and a.decided_index < 400 and b is not None:
                self.assertEqual(a, b)
