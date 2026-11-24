"""Bybit candles (owner's exchange, last price fallback), the one-source trading history, and automatic backups."""

import json
import sqlite3
from contextlib import closing
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from src.analysis.primary_history import get_trading_history
from src.data_collection.backup import backup_database
from src.data_collection.bybit_provider import BybitProvider
from src.data_collection.exchange_updater import update_all_exchanges
from src.data_collection.market_data import MarketData
from src.data_collection.market_data_repository import MarketDataRepository
from tests.helpers import hourly_candles

H = timedelta(hours=1)
T0 = datetime(2026, 11, 20, 0, tzinfo=timezone.utc)


def response(rows, code=0):
    return BytesIO(json.dumps({"retCode": code, "retMsg": "OK", "result": {"list": rows}}).encode())


def row(t, close):
    return [str(int(t.timestamp() * 1000)), str(close - 1), str(close + 5), str(close - 5), str(close), "12.5", "999"]


class TestBybitProvider(unittest.TestCase):

    @patch("src.data_collection.bybit_provider.time.sleep")
    @patch("src.data_collection.bybit_provider.urlopen")
    def test_parses_newest_first_and_drops_the_forming_candle(self, urlopen, _sleep):
        urlopen.return_value = response([row(T0 + 3 * H, 103), row(T0 + 2 * H, 102), row(T0 + H, 101), row(T0, 100)])
        now = T0 + 3 * H + timedelta(minutes=20)  # the 03:00 candle is still forming
        candles = BybitProvider().fetch_candles("BTC/USDT", "1h", T0, T0 + 4 * H, now=now)
        self.assertEqual([c.timestamp for c in candles], [T0, T0 + H, T0 + 2 * H])
        self.assertEqual(candles[0].close, 100.0)
        self.assertEqual(candles[0].exchange, "bybit")
        url = urlopen.call_args[0][0].full_url
        self.assertTrue(url.startswith("https://api.bybit.eu/v5/market/kline?"))
        self.assertIn("category=spot", url)
        self.assertIn("symbol=BTCUSDT", url)
        self.assertIn("interval=60", url)

    @patch("src.data_collection.bybit_provider.time.sleep")
    @patch("src.data_collection.bybit_provider.urlopen")
    def test_falls_back_to_the_global_address(self, urlopen, _sleep):
        urlopen.side_effect = [OSError("403 blocked"), response([row(T0, 100)])]
        candles = BybitProvider().fetch_candles("BTC/USDT", "1h", T0, T0 + H, now=T0 + 2 * H)
        self.assertEqual(len(candles), 1)
        self.assertTrue(urlopen.call_args[0][0].full_url.startswith("https://api.bybit.com/"))

    @patch("src.data_collection.bybit_provider.time.sleep")
    @patch("src.data_collection.bybit_provider.urlopen")
    def test_pages_of_1000_hours(self, urlopen, _sleep):
        urlopen.side_effect = lambda *a, **k: response([])
        BybitProvider().fetch_candles("BTC/USDT", "1h", T0 - 2500 * H, T0, now=T0)
        self.assertEqual(urlopen.call_count, 3)

    @patch("src.data_collection.bybit_provider.urlopen")
    def test_api_error_is_reported(self, urlopen):
        urlopen.return_value = response([], code=10001)
        with self.assertRaises(RuntimeError):
            BybitProvider().fetch_candles("BTC/USDT", "1h", T0, T0 + H, now=T0 + 2 * H)


class FakeBybit:
    exchange = "bybit"

    def __init__(self):
        self.requests = []

    def fetch_candles(self, symbol, timeframe, start, end):
        self.requests.append((symbol, start, end))
        return [MarketData("BTC/USDT", "crypto", start + k * H, 1.0, 1.0, 1.0, 1.0, 1.0, "bybit") for k in range(3)]


class TestUpdaterAndBackup(unittest.TestCase):

    def test_first_bybit_update_downloads_from_2021_and_backs_up_first(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = MarketDataRepository(Path(folder) / "market_data.db")
            repo.save_candles(hourly_candles([100.0, 101.0]), timeframe="1h")
            fake = FakeBybit()
            update_all_exchanges(repo, log=lambda *a: None, providers=(fake,))
            symbol, start, _ = fake.requests[0]
            self.assertEqual(symbol, "BTC/USDT")
            self.assertEqual(start, BybitProvider.FIRST_AVAILABLE)
            self.assertIsNotNone(repo.get_latest_candle_timestamp(symbol="BTC/USDT", market="crypto",
                                                                  timeframe="1h", exchange="bybit"))
            backups = list((Path(folder) / "backups").glob("market_data_*.db"))
            self.assertEqual(len(backups), 1)
            # the backup was taken BEFORE the update: it has no Bybit rows
            with closing(sqlite3.connect(backups[0])) as c:
                self.assertEqual(c.execute("SELECT COUNT(*) FROM market_candles WHERE exchange='bybit'").fetchone()[0], 0)

    def test_backup_once_a_day_and_keep_the_newest(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "x.db"
            with closing(sqlite3.connect(db)) as c:
                c.execute("CREATE TABLE t (a)")
                c.commit()
            for day in range(1, 11):
                self.assertIsNotNone(backup_database(db, keep=3, today=datetime(2026, 11, day, tzinfo=timezone.utc)))
            self.assertIsNone(backup_database(db, keep=3, today=datetime(2026, 11, 10, 18, tzinfo=timezone.utc)))
            names = sorted(p.name for p in (Path(folder) / "backups").iterdir())
            self.assertEqual(names, ["x_2026-11-08.db", "x_2026-11-09.db", "x_2026-11-10.db"])


class TestTradingHistory(unittest.TestCase):
    """One price source (Bitstamp, the longest history); only its missing hours come from Kraken, Coinbase, Bybit."""

    def test_bitstamp_everywhere_and_gaps_filled_in_size_order(self):
        start = datetime(2026, 11, 14, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as folder:
            repo = MarketDataRepository(Path(folder) / "m.db")
            closes = [100.0 + k for k in range(8)]
            repo.save_candles([c for k, c in enumerate(hourly_candles(closes, start=start, exchange="bitstamp"))
                               if k not in (2, 3, 5)], timeframe="1h")
            repo.save_candles([c for k, c in enumerate(hourly_candles([200.0 + k for k in range(8)], start=start,
                                                                      exchange="kraken")) if k != 3], timeframe="1h")
            repo.save_candles(hourly_candles([300.0 + k for k in range(8)], start=start, exchange="coinbase"),
                              timeframe="1h")
            repo.save_candles(hourly_candles([400.0 + k for k in range(8)], start=start, exchange="bybit",
                                             symbol="BTC/USDT"), timeframe="1h")
            h = get_trading_history(repo, start, start + 8 * H)
        self.assertEqual([c.close for c in h.candles], [100, 101, 202, 303, 104, 205, 106, 107])
        self.assertEqual([h.sources[c.timestamp] for c in h.candles],
                         ["bitstamp", "bitstamp", "kraken", "coinbase", "bitstamp", "kraken", "bitstamp", "bitstamp"])
        self.assertEqual(len(h.substituted_hours()), 3)  # filled hours: never traded on
        self.assertTrue(all(c.exchange == "primary" and c.symbol == "BTC/USD" for c in h.candles))

    def test_bybit_is_the_last_fallback(self):
        start = datetime(2026, 11, 14, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as folder:
            repo = MarketDataRepository(Path(folder) / "m.db")
            repo.save_candles([c for k, c in enumerate(hourly_candles([100.0, 101.0, 102.0], start=start,
                                                                      exchange="bitstamp")) if k != 1], timeframe="1h")
            repo.save_candles(hourly_candles([400.0, 401.0, 402.0], start=start, exchange="bybit", symbol="BTC/USDT"),
                              timeframe="1h")
            h = get_trading_history(repo, start, start + 3 * H)
        self.assertEqual([c.close for c in h.candles], [100.0, 401.0, 102.0])
        self.assertEqual(h.sources[start + H], "bybit")


if __name__ == "__main__":
    unittest.main()
