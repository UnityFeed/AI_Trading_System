"""Learning engine v3: setting versions, self-correction, memorised passes, all timeframes, training cache."""

import math
import random
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.analysis.technical_indicators import calculate_indicators
from src.analysis.timeframes import aggregate_hourly_candles
from src.backtesting.market import Market
from src.data_collection.market_data import MarketData
from src.predictive_engine import learner, mtf, training
from src.predictive_engine.forecast_log import timeframe_of
from src.predictive_engine.service import EngineService, horizon_label
from tests.test_predictive_tools import market as daily_market
from tests.test_predictive_tools import walk


START = datetime(2016, 1, 4, tzinfo=timezone.utc)  # a Monday


def hours(n, seed=5):
    rng = random.Random(seed)
    price, out = 400.0, []
    for k in range(n):
        new = price * math.exp(rng.gauss(0.00003, 0.006))
        out.append(MarketData("BTC/USD", "crypto", START + timedelta(hours=k), price, max(price, new) * 1.001,
                              min(price, new) * 0.999, new, 10.0 + rng.random(), "primary"))
        price = new
    return out


def build(c, tf):
    return Market(tf, c, calculate_indicators(c, tf), [True] * len(c),
                  [False] + [c[i].timestamp - c[i - 1].timestamp == c[1].timestamp - c[0].timestamp
                             for i in range(1, len(c))])


def markets_from(hourly):
    out = {"1h": build(hourly, "1h")}
    for tf in ("4h", "1d", "1w"):
        out[tf] = build(aggregate_hourly_candles(hourly, tf).candles, tf)
    return out


class TestConfigsAndCalibration(unittest.TestCase):

    def test_every_version_is_causal(self):
        """Re-study, self-correction and fast settings use nothing from after the forecast candle."""
        c = walk(800)
        cut = 620
        full, part = daily_market(c), daily_market(c[:cut])
        inputs_full, inputs_part = learner.build_inputs(full), learner.build_inputs(part)
        for config in (learner.CONFIGS[1], learner.CONFIGS[8], learner.CONFIGS[9]):
            a = learner.replay(full, 14, *inputs_full, config=config)
            b = learner.replay(part, 14, *inputs_part, config=config)
            checked = 0
            for i in range(cut):
                self.assertEqual(a.forecasts[i] is None, b.forecasts[i] is None)
                if a.forecasts[i] is not None:
                    checked += 1
                    self.assertAlmostEqual(sum(a.forecasts[i].values()), 1.0, places=9)
                    for k in learner.KINDS:
                        self.assertAlmostEqual(a.forecasts[i][k], b.forecasts[i][k], places=9)
            self.assertGreater(checked, 300, config.name)

    def test_calibrator_corrects_an_overconfident_forecast(self):
        cal = learner.Calibrator(bins=10, prior=10)
        said = {"bull": 0.8, "bear": 0.1, "range": 0.1}
        for k in range(400):  # it said 80% bull, but bull happened only half of the time
            cal.learn(said, "bull" if k % 2 else "range")
        fixed = cal.apply(said)
        self.assertLess(fixed["bull"], 0.6)
        self.assertGreater(fixed["range"], 0.3)
        self.assertAlmostEqual(sum(fixed.values()), 1.0, places=9)

    def test_nested_choice_uses_only_earlier_years(self):
        per_year = [
            {2017: (100, 60.0, 60.0), 2018: (100, 50.0, 60.0), 2019: (100, 70.0, 60.0)},  # good only in 2018
            {2017: (100, 55.0, 60.0), 2018: (100, 65.0, 60.0), 2019: (100, 50.0, 60.0)},  # good in 2017 and 2019
        ]
        chosen, table = learner.choose_by_year(per_year, ["a", "b"])
        self.assertEqual(chosen[2017], 0)  # nothing earlier: first version
        self.assertEqual(chosen[2018], 1)  # b was better in 2017
        self.assertEqual(chosen[2019], 0)  # a was better over 2017-2018 (skill +5.8% vs -0%)
        self.assertEqual([x["config"] for x in table], ["a", "b", "a"])

    def test_memorised_pass_starts_with_what_the_first_pass_learned(self):
        c = walk(700)
        m = daily_market(c)
        inputs = learner.build_inputs(m)
        honest, memorised = learner.passes(m, 7, *inputs, count=2)
        self.assertEqual(memorised.state["seen"], 2 * honest.state["seen"])
        later = [i for i in range(len(c)) if honest.forecasts[i] is not None]
        self.assertTrue(any(abs(honest.forecasts[i]["bull"] - memorised.forecasts[i]["bull"]) > 1e-6 for i in later))


class TestAllTimeframes(unittest.TestCase):

    def test_multi_timeframe_inputs_never_see_the_future(self):
        """Cut the hourly data in the middle of a day and a week: earlier 4h rows stay exactly the same."""
        h = hours(24 * 7 * 40)
        cut = 24 * 7 * 30 + 24 * 3 + 13
        full, part = markets_from(h), markets_from(h[:cut])
        names, rows, keys = mtf.tf_inputs(full, "4h")
        names2, rows2, keys2 = mtf.tf_inputs(part, "4h")
        self.assertEqual(names, names2)
        self.assertTrue({"1d.trend", "1d.adx", "1w.ema200", "own.rsi"} <= set(names))
        n = len(part["4h"].candles)
        for i in range(n):
            self.assertEqual(rows[i], rows2[i], i)
            self.assertEqual(keys["regime"][i], keys2["regime"][i])

    def test_higher_timeframe_is_the_last_completed_candle(self):
        h = hours(24 * 7 * 30)
        m = markets_from(h)
        names, rows, _ = mtf.tf_inputs(m, "4h")
        k = names.index("1d.rsi")
        daily = m["1d"]
        for i, c in enumerate(m["4h"].candles[-30:], start=len(m["4h"].candles) - 30):
            closes_at = c.timestamp + timedelta(hours=4)
            done = [j for j, d in enumerate(daily.candles) if d.timestamp + timedelta(days=1) <= closes_at]
            rsi = daily.rows[done[-1]].values.get("rsi_14")
            self.assertAlmostEqual(rows[i][k], (rsi - 50) / 50, places=12)

    def test_horizon_labels(self):
        self.assertEqual(horizon_label("1h", 24), "1 day")
        self.assertEqual(horizon_label("4h", 42), "7 days")
        self.assertEqual(horizon_label("1d", 30), "30 days")
        self.assertEqual(horizon_label("1h", 6), "6 hours")
        self.assertEqual(timeframe_of("learner-v3-4h-h42"), "4h")
        self.assertEqual(timeframe_of("learner-v2-h30"), "1d")


class TestTrainingSession(unittest.TestCase):

    def test_pack_round_trip(self):
        values = [None, {"bull": 0.2, "bear": 0.3, "range": 0.5}]
        col = training.Column.pack(values, learner.KINDS)
        self.assertEqual(len(col), 2)
        self.assertIsNone(col[0])
        self.assertEqual(col[1], values[1])
        self.assertEqual(col[-1], values[1])
        self.assertEqual(list(col), [None, values[1]])

    def test_session_cache_feeds_the_app_and_new_candles_are_learned_live(self):
        h = hours(24 * 7 * 40)
        markets = markets_from(h)
        cache = training.new_cache()
        cache["timeframes"]["4h"] = training.train_timeframe(markets, "4h", horizons=(6,), configs=2, memorised=1)
        part = cache["timeframes"]["4h"]["horizons"][6]
        self.assertEqual(len(part["configs"]), 2)
        self.assertEqual(len(part["memorised"]), 1)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cache.pkl"
            training.save(cache, path)
            loaded = training.load(path)
        self.assertIsNotNone(loaded)

        def svc(m):
            s = EngineService(m["1d"], h[:len(m["1h"].candles)], markets=m, cache=loaded, timeframes=())
            s.horizons = lambda tf: (6,)
            return s

        same = svc(markets)
        now = same.scenarios(6, timeframe="4h")
        r = part["replay"]
        last = max(i for i in range(len(r.forecasts)) if r.forecasts[i] is not None)
        self.assertEqual(now["candle_time"], markets["4h"].candles[last].timestamp.isoformat())
        self.assertAlmostEqual(now["scenarios"][0]["probability"], round(max(r.forecasts[last].values()), 4))
        self.assertEqual(now["training"]["version_now"], part["current_config"])

        # more data than the training session saw: old candles from the session, new ones learned live
        h2 = h + hours(24 * 7 * 42)[len(h):]
        longer = markets_from(h2)
        later = svc(longer)
        old = later.scenarios(6, markets["4h"].candles[last].timestamp, timeframe="4h")
        self.assertEqual(old["scenarios"], now["scenarios"])
        newest = later.scenarios(6, timeframe="4h")
        self.assertGreater(newest["candle_time"], now["candle_time"])


if __name__ == "__main__":
    unittest.main()
