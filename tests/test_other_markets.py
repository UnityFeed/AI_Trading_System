"""Other markets (S&P 500, Nasdaq 100, Dow 30, gold, silver): download, storage and AI features without look-ahead."""

import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

from src.backtesting.market import Market
from src.data_collection.other_markets import OtherMarketsStore, fetch_yahoo, update_other_markets
from src.data_collection.market_data import MarketData
from src.research.other_market_features import daily_features, other_market_features


def yahoo_payload(days, closes, tz="America/New_York"):
    # Yahoo stamps daily bars at the session open (09:30 New York = 14:30 UTC in winter)
    stamps = [int(datetime(d.year, d.month, d.day, 14, 30, tzinfo=timezone.utc).timestamp()) for d in days]
    return {"chart": {"result": [{
        "meta": {"exchangeTimezoneName": tz},
        "timestamp": stamps,
        "indicators": {"quote": [{"open": closes, "high": closes, "low": closes, "close": closes,
                                  "volume": [1] * len(closes)}]},
    }], "error": None}}


class FakeOpen:
    def __init__(self, payload):
        self.payload = payload

    def __call__(self, request, timeout=None):
        return BytesIO(json.dumps(self.payload).encode())


class TestDownloadAndStore(unittest.TestCase):

    def test_todays_forming_bar_and_empty_closes_are_dropped(self):
        days = [date(2026, 11, 19), date(2026, 11, 20), date(2026, 11, 23), date(2026, 11, 24)]
        payload = yahoo_payload(days, [100.0, None, 102.0, 103.0])
        now = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)  # 13:00 in New York: the 24th is still trading
        bars = fetch_yahoo("^GSPC", now=now, opener=FakeOpen(payload))
        self.assertEqual([b["day"] for b in bars], [date(2026, 11, 19), date(2026, 11, 23)])

    def test_first_value_is_kept_and_changes_are_noted(self):
        with tempfile.TemporaryDirectory() as folder:
            store = OtherMarketsStore(Path(folder) / "o.db")
            day = date(2026, 11, 20)
            self.assertEqual(store.save("spx", [{"day": day, "close": 100.0}]), (1, 0))
            self.assertEqual(store.save("spx", [{"day": day, "close": 100.0}]), (0, 0))
            self.assertEqual(store.save("spx", [{"day": day, "close": 101.0}]), (0, 1))
            self.assertEqual(store.closes("spx"), {day: 100.0})
            self.assertEqual(list(store.load_all()), ["mkt.spx"])

    def test_one_market_failing_does_not_stop_the_others(self):
        with tempfile.TemporaryDirectory() as folder:
            store = OtherMarketsStore(Path(folder) / "o.db")
            calls = []

            def fetch(symbol):
                calls.append(symbol)
                if symbol == "^NDX":
                    raise RuntimeError("blocked")
                return [{"day": date(2026, 11, 20), "close": 1.0}]

            lines = []
            import src.data_collection.other_markets as om
            sleep = om.time.sleep
            om.time.sleep = lambda s: None
            try:
                update_other_markets(store, log=lines.append, fetch=fetch)
            finally:
                om.time.sleep = sleep
            self.assertEqual(len(calls), 5)
            self.assertTrue(any("FAILED" in line for line in lines))
            self.assertEqual(len(store.load_all()), 4)


def btc(n, tf="1d", start=datetime(2026, 1, 1, tzinfo=timezone.utc)):
    step = timedelta(days=1) if tf == "1d" else timedelta(hours=4)
    c = [MarketData("BTC/USD", "crypto", start + k * step, 1, 1, 1, 1, 1, "primary") for k in range(n)]
    return Market(tf, c, [], [True] * n, [False] + [True] * (n - 1))


class TestFeatures(unittest.TestCase):

    def test_daily_features(self):
        closes = {date(2025, 1, 1) + timedelta(days=k): 100.0 * (1.01 ** k) for k in range(250)}
        f = daily_features(closes)
        last = max(closes)
        self.assertAlmostEqual(f["ret5"][last], 5 * 0.00995033, places=6)
        self.assertGreater(f["trend200"][last], 0)
        self.assertAlmostEqual(f["vol20"][last], 0.0, places=9)  # constant growth: no volatility

    def test_a_trading_day_is_used_only_after_it_ended(self):
        day = date(2026, 1, 5)  # Monday
        closes = {date(2025, 12, 1) + timedelta(days=k): 100.0 + k for k in range(36)}  # up to Jan 5
        ext = {"mkt.spx": closes}
        daily = btc(10)
        values = other_market_features(daily, ext, mode="full")["mkt.spx.ret1"]
        index = {c.timestamp.date(): k for k, c in enumerate(daily.candles)}
        # BTC's candle of Jan 4 (closes Jan 5 00:00 UTC) must not see Jan 5's close; Jan 5's candle may
        jan4, jan5 = values[index[date(2026, 1, 4)]], values[index[day]]
        self.assertNotEqual(jan4, jan5)
        self.assertAlmostEqual(jan5, daily_features(closes)["ret1"][day])
        # on 4h candles: the Jan 5 close becomes usable only for candles closing on Jan 6 or later
        h4 = btc(20, "4h", start=datetime(2026, 1, 5, tzinfo=timezone.utc))
        v4 = other_market_features(h4, ext, mode="full")["mkt.spx.ret1"]
        for k, c in enumerate(h4.candles):
            close_time = c.timestamp + timedelta(hours=4)
            if close_time < datetime(2026, 1, 6, tzinfo=timezone.utc):
                self.assertNotEqual(v4[k], daily_features(closes)["ret1"][day])


    def test_compact_mode_averages_the_stock_indices(self):
        days = {date(2025, 1, 1) + timedelta(days=k): k for k in range(60)}
        ext = {"mkt.spx": {d: 100.0 + k for d, k in days.items()}, "mkt.ndx": {d: 200.0 + 3 * k for d, k in days.items()},
               "mkt.gold": {d: 50.0 for d in days}}
        names = set(other_market_features(btc(5, start=datetime(2025, 3, 1, tzinfo=timezone.utc)), ext, mode="compact"))
        self.assertEqual(names, {"mkt.stocks.ret5", "mkt.stocks.ret20", "mkt.stocks.vol20", "mkt.gold.ret20"})
        self.assertEqual(other_market_features(btc(5), ext, mode="off"), {})


if __name__ == "__main__":
    unittest.main()
