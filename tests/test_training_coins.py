"""Training coins (ETH, BNB, XRP, SOL, TRX): download, storage, and pooled pattern experts without look-ahead."""

import json
import math
import random
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

from src.data_collection.market_data import MarketData
from src.data_collection.market_data_repository import MarketDataRepository
from src.data_collection.training_coins import COINS, coin_histories, fetch_klines, update_training_coins
from src.predictive_engine import ml_experts, training
from src.predictive_engine.outcomes import outcomes
from tests.test_predictive_learning import hours, markets_from

H = timedelta(hours=1)
T0 = datetime(2026, 11, 20, tzinfo=timezone.utc)


class Opener:
    def __init__(self, rows):
        self.rows, self.urls = rows, []

    def __call__(self, request, timeout=None):
        self.urls.append(request.full_url)
        return BytesIO(json.dumps(self.rows).encode())


def kline(t, close):
    ms = int(t.timestamp() * 1000)
    return [ms, str(close), str(close + 1), str(close - 1), str(close), "5.0", ms + 3599999, "0", 1, "0", "0", "0"]


class TestDownload(unittest.TestCase):

    def test_completed_candles_only(self):
        opener = Opener([kline(T0, 10), kline(T0 + H, 11), kline(T0 + 2 * H, 12)])
        candles = fetch_klines("ETH", T0, T0 + 3 * H, now=T0 + 2 * H + timedelta(minutes=5), opener=opener, delay=0)
        self.assertEqual([c.close for c in candles], [10.0, 11.0])
        self.assertEqual(candles[0].symbol, "ETH/USDT")
        self.assertEqual(candles[0].exchange, "binance")
        self.assertIn("data-api.binance.vision/api/v3/klines?symbol=ETHUSDT&interval=1h", opener.urls[0])

    def test_update_saves_into_its_own_database_and_continues_forward(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = MarketDataRepository(Path(folder) / "coins.db")
            asked = []

            def fetch(coin, start, end):
                asked.append((coin, start))
                return [MarketData(f"{coin}/USDT", "crypto", T0 + k * H, 1, 1, 1, 1, 1, "binance") for k in range(3)]

            update_training_coins(repo, log=lambda *a: None, fetch=fetch)
            self.assertEqual([c for c, _ in asked], list(COINS))
            asked.clear()
            update_training_coins(repo, log=lambda *a: None, fetch=fetch)
            self.assertEqual(asked[0][1], T0 + 3 * H)  # forward from the last stored candle


class TestPooledExperts(unittest.TestCase):

    @unittest.skipUnless(ml_experts.available(), "libraries not installed")
    def test_coins_add_examples_but_never_from_the_future(self):
        btc = markets_from(hours(24 * 7 * 60, seed=5))
        coin = markets_from(hours(24 * 7 * 60, seed=9))
        names, rows, _ = training.pattern_inputs(btc, "4h", training.inputs_for(btc, "4h"))
        coins = training.coin_rows({"ETH": coin}, "4h", names)
        out = outcomes(btc["4h"], 6)
        full = training.pattern_experts(rows, out, "4h", btc["4h"], coins, horizon=6)
        alone = training.pattern_experts(rows, out, "4h", btc["4h"], (), horizon=6)
        changed = [i for i, (a, b) in enumerate(zip(full["trees"], alone["trees"]))
                   if a is not None and b is not None and abs(a["bull"] - b["bull"]) > 1e-6]
        self.assertTrue(changed)  # the coin's examples change what the trees learn

        # cut the COIN's data in time: forecasts before the cut must not change
        cut = len(btc["4h"].candles) * 2 // 3
        cut_time = btc["4h"].candles[cut].timestamp
        short = {tf: m for tf, m in markets_from([h for h in hours(24 * 7 * 60, seed=9) if h.timestamp < cut_time]).items()}
        coins_short = training.coin_rows({"ETH": short}, "4h", names)
        part = training.pattern_experts(rows, out, "4h", btc["4h"], coins_short, horizon=6)
        for i in range(cut - 6):
            for name in ("trees", "analog"):
                a, b = full[name][i], part[name][i]
                self.assertEqual(a is None, b is None)
                if a is not None:
                    for k in a:
                        self.assertAlmostEqual(a[k], b[k], places=9, msg=(name, i))

    def test_coin_histories_skip_empty_and_short_coins(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = MarketDataRepository(Path(folder) / "coins.db")
            rng = random.Random(1)
            price, candles = 100.0, []
            for k in range(24 * 401):
                price *= math.exp(rng.gauss(0, 0.01))
                candles.append(MarketData("ETH/USDT", "crypto", datetime(2024, 1, 1, tzinfo=timezone.utc) + k * H,
                                          price, price, price, price, 0.0 if k == 5 else 3.0, "binance"))
            repo.save_candles(candles, timeframe="1h")
            histories = coin_histories(repo)
            self.assertEqual(list(histories), ["ETH"])
            self.assertEqual(len(histories["ETH"].candles), 24 * 401 - 1)  # the zero-volume hour is skipped


if __name__ == "__main__":
    unittest.main()
