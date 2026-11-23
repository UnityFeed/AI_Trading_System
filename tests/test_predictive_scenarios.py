import math
import random
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.analysis.technical_indicators import calculate_indicators
from src.backtesting.market import Market
from src.data_collection.market_data import MarketData
from src.predictive_engine import engine
from src.predictive_engine.forecast_log import ForecastLog
from src.predictive_engine.scenarios import KINDS, known_before, predict, score, walk_forward


START = datetime(2014, 1, 6, tzinfo=timezone.utc)


def market(days=1500, seed=4):
    rng = random.Random(seed)
    price, candles = 100.0, []
    for k in range(days):
        open_ = price
        price *= math.exp(rng.gauss(0.001, 0.03))
        candles.append(MarketData("BTC/USD", "crypto", START + timedelta(days=k), open_, max(open_, price) * 1.01,
                                  min(open_, price) * 0.99, price, 1000.0, "primary"))
    return Market("1d", candles, calculate_indicators(candles, "1d"), [True] * days, [False] + [True] * (days - 1))


class TestScenarioModels(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.market = market()
        cls.ctx = engine.engine_context(cls.market)

    def test_probabilities_add_up_and_learn_only_from_decided_outcomes(self):
        i = 1200
        train = known_before(self.ctx, i)
        self.assertTrue(train)
        self.assertTrue(all(self.ctx.outcomes[j].decided_index < i for j in train))
        for model in ("base", "structure", "analog"):
            f = predict(self.ctx, i, train, model)
            self.assertAlmostEqual(sum(f.probabilities[k] for k in KINDS), 1.0, places=9)

    def test_walk_forward_scores(self):
        forecasts = walk_forward(self.ctx, "structure", first_year=2016)
        self.assertTrue(forecasts)
        self.assertTrue(all(self.market.candles[f.index].timestamp.year >= 2016 for f in forecasts))
        s = score(self.ctx, forecasts)
        self.assertTrue(0 <= s.brier <= 2)

    def test_todays_scenarios(self):
        d = engine.todays_scenarios(self.market, self.ctx).as_dict()
        self.assertEqual([s["kind"] for s in d["scenarios"]],
                         sorted(KINDS, key=lambda k: -next(s["probability"] for s in d["scenarios"] if s["kind"] == k)))
        self.assertGreater(d["target"], d["close"])
        self.assertLess(d["stop"], d["close"])
        self.assertTrue(all(s["proven_wrong_by"] for s in d["scenarios"]))


class TestForecastLog(unittest.TestCase):

    def test_first_forecast_stays_and_outcomes_are_scored(self):
        m = market(300, seed=8)
        ctx = engine.engine_context(m)
        with tempfile.TemporaryDirectory() as folder:
            log = ForecastLog(Path(folder) / "predictions.db")
            short = Market("1d", m.candles[:200], m.rows[:200], m.tradeable[:200], m.consecutive[:200])
            first = engine.todays_scenarios(short, engine.engine_context(short)).as_dict()
            self.assertTrue(log.record(first))
            changed = dict(first, close=1.0)
            self.assertFalse(log.record(changed))  # never overwritten
            self.assertEqual(log.history()[0]["close"], first["close"])
            self.assertEqual(log.score_pending(m.candles[:210]), 0 if all(
                first["stop"] < c.close < first["target"] for c in m.candles[200:210]) else 1)
            log.score_pending(m.candles)  # 100 days later: decided either way
            record = log.track_record()
            self.assertEqual(record["scored"], 1)
            self.assertIn(log.history()[0]["outcome"], KINDS)
            del ctx


if __name__ == "__main__":
    unittest.main()
