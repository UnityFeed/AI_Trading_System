import json
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from src.analysis.primary_history import get_continuous_history
from src.app.chart_data import build_series, chunk, trade_markers
from src.app.server import AppState, serve
from src.data_collection.market_data_repository import MarketDataRepository
from src.paper_trading.store import Fill, PaperTradingStore
from tests.helpers import hourly_candles


START = datetime(2026, 1, 1, tzinfo=timezone.utc)
HOURS = 24 * 40


def make_repository(folder: Path) -> MarketDataRepository:
    repository = MarketDataRepository(folder / "market.db")
    closes = [100 + (i % 50) for i in range(HOURS)]
    for exchange in ("kraken", "coinbase"):
        candles = hourly_candles(closes, start=START, exchange=exchange,
                                 skip_hours={30} if exchange == "kraken" else None)
        repository.save_candles(candles=candles, timeframe="1h")
    return repository


class TestChartData(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        repository = make_repository(Path(self.temp_dir.name))
        self.history = get_continuous_history(repository, START, START + timedelta(hours=HOURS))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_series_rows_and_filled_flag(self):

        series = build_series(self.history, "1h")

        self.assertEqual(len(series.rows), HOURS)
        self.assertEqual(series.rows[0][0], int(START.timestamp()))
        # Hour 30 came from Coinbase (Kraken missing), so it is flagged.
        self.assertTrue(series.rows[30][6])
        self.assertFalse(series.rows[29][6])
        self.assertIsNone(series.indicators["ema_200"][0])
        self.assertIsNotNone(series.indicators["ema_200"][-1])

    def test_daily_filled_flag_marks_the_whole_day(self):

        series = build_series(self.history, "1d")

        self.assertTrue(series.rows[1][6])   # day 2 contains hour 30
        self.assertFalse(series.rows[0][6])

    def test_chunks_walk_back_in_time(self):

        series = build_series(self.history, "1h")

        newest = chunk(series, None, 100)
        self.assertEqual(len(newest["candles"]), 100)
        self.assertEqual(newest["candles"][-1], series.rows[-1])
        self.assertTrue(newest["has_more"])
        self.assertEqual(len(newest["indicators"]["rsi_14"]), 100)

        older = chunk(series, newest["candles"][0][0], 100)
        self.assertEqual(older["candles"][-1][0], newest["candles"][0][0] - 3600)

        first = chunk(series, series.rows[50][0], 100)
        self.assertEqual(len(first["candles"]), 50)
        self.assertFalse(first["has_more"])

    def test_trade_markers_sit_on_the_candle_that_contains_the_fill(self):

        fill = Fill(1, 1, START + timedelta(hours=27), "buy", 101.0, 0, 1, 0, 1)

        self.assertEqual(trade_markers([fill], "1d")[0]["time"], int((START + timedelta(days=1)).timestamp()))
        self.assertEqual(trade_markers([fill], "4h")[0]["time"], int((START + timedelta(hours=24)).timestamp()))


class TestServer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        folder = Path(cls.temp_dir.name)
        repository = make_repository(folder)
        store = PaperTradingStore(folder / "paper.db")
        now = START + timedelta(hours=HOURS)
        with patch("src.app.routine.datetime") as fake:
            fake.now.return_value = now
            fake.side_effect = lambda *a, **k: datetime(*a, **k)
            cls.state = AppState(repository, store)
        cls.server = serve(cls.state, port=0)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.temp_dir.cleanup()

    def get(self, path):
        with urlopen(f"http://127.0.0.1:{self.port}{path}") as response:
            return response.status, response.read().decode("utf-8")

    def post(self, path, headers=None):
        request = Request(f"http://127.0.0.1:{self.port}{path}", method="POST", headers=headers or {})
        try:
            with urlopen(request) as response:
                return response.status, json.loads(response.read())
        except HTTPError as error:
            return error.code, json.loads(error.read())

    def test_pages(self):

        status, page = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("run-btn", page)
        self.assertIn("<h2>Your data</h2>", page)

        status, page = self.get("/chart")
        self.assertEqual(status, 200)
        self.assertIn("lightweight-charts@5.2.1", page)

    def test_chart_api(self):

        status, body = self.get("/api/chart?tf=4h&limit=10")
        data = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(len(data["candles"]), 10)
        self.assertIn("macd_hist", data["indicators"])
        self.assertIn("markers", data)

        with self.assertRaises(HTTPError):
            self.get("/api/chart?tf=2h")

    def test_strategy_tester_routes(self):

        status, page = self.get("/strategy")
        self.assertEqual(status, 200)
        self.assertIn("Strategy tester", page)

        strategies = json.loads(self.get("/api/strategies")[1])
        self.assertIn(strategies["active"], [s["id"] for s in strategies["strategies"]])

        report = json.loads(self.get(f"/api/backtest?strategy={strategies['active']}&fee=0.4")[1])
        self.assertEqual(report["costs"]["fee_pct"], 0.4)
        self.assertIn("years", report)

        chart = json.loads(self.get(f"/api/chart?tf=1d&trades={strategies['active']}")[1])
        self.assertIn("markers", chart)
        self.assertEqual(json.loads(self.get("/api/chart?tf=1d&trades=none")[1])["markers"], [])

        years = strategies["start_years"]
        self.assertTrue(years)
        from_year = json.loads(self.get(f"/api/backtest?strategy={strategies['active']}&start={years[-1]}")[1])
        self.assertEqual(from_year["start"], f"{years[-1]}-01-01")
        self.assertIn("by_start_year", from_year)

        for bad in ("/api/backtest?strategy=nope", "/api/backtest?fee=0.1", "/api/chart?trades=nope",
                    "/api/backtest?start=1999", "/api/backtest?start=abc"):
            with self.assertRaises(HTTPError):
                self.get(bad)

    def test_overview_and_strategy_state(self):

        status, page = self.get("/")
        self.assertIn("latest-trade", page)
        self.assertIn("SelectedStrategy", page)

        active = json.loads(self.get("/api/strategies")[1])["active"]
        state = json.loads(self.get(f"/api/strategy-state?strategy={active}")[1])
        self.assertEqual(state["strategy"]["id"], active)
        self.assertIn("rules", state)
        self.assertIn("position", state)

        with self.assertRaises(HTTPError):
            self.get("/api/strategy-state?strategy=nope")

    def test_compare_and_graded_strategies(self):

        strategies = json.loads(self.get("/api/strategies")[1])["strategies"]
        kinds = {s["id"]: s["kind"] for s in strategies}
        self.assertIn("exposure", kinds.values())
        graded = next(s for s in strategies if s["kind"] == "exposure" and s["id"] == "sma-ensemble-1d")
        self.assertFalse(graded["supports_margin"])

        compare = json.loads(self.get("/api/compare?fee=0.25&start=all")[1])
        self.assertEqual(len(compare["rows"]), len(strategies))
        by_id = {r["id"]: r for r in compare["rows"]}
        # No external data in this test: those strategies say so instead of failing.
        self.assertIn("error", by_id["sma-mvrv-1d"])
        self.assertIn("sharpe", by_id["sma-ensemble-1d"])
        self.assertIn("sharpe", compare["buy_and_hold"])

        state = json.loads(self.get("/api/strategy-state?strategy=sma-ensemble-1d")[1])
        self.assertEqual(state["kind"], "exposure")
        with self.assertRaises(HTTPError) as missing:
            self.get("/api/strategy-state?strategy=sma-mvrv-1d")
        self.assertEqual(missing.exception.code, 409)
        with self.assertRaises(HTTPError):
            self.get("/api/compare?fee=0.1")

    def test_scenarios_api(self):

        # the AI is prepared in the background: first "learning", then the answer
        # (40 days of test data are too few for the learning engine's first forecast)
        data = json.loads(self.get("/api/scenarios?h=7")[1])
        for _ in range(100):
            if data.get("status") != "learning":
                break
            time.sleep(0.2)
            data = json.loads(self.get("/api/scenarios?h=7")[1])
        self.assertIn("error", data)
        self.assertNotIn("track_record", data)  # no forecast log given in this test: nothing recorded
        tools = json.loads(self.get("/api/tools?tf=4h")[1])
        for key in ("zones", "patterns", "regime", "volume_profile", "fibonacci"):
            self.assertIn(key, tools)
        for bad in ("/api/scenarios?h=5", "/api/tools?tf=2h", "/api/tools?until=yesterday"):
            with self.assertRaises(HTTPError):
                self.get(bad)

    def test_structure_api(self):

        data = json.loads(self.get("/api/structure?tf=4h")[1])
        self.assertIn(data["trend"], ("up", "down", "none"))
        self.assertIn("pivots", data)
        self.assertIn("events", data)
        with self.assertRaises(HTTPError):
            self.get("/api/structure?tf=2h")

    def test_buttons_need_the_app_header(self):

        status, _ = self.post("/api/run?update=0")
        self.assertEqual(status, 403)

    def test_run_job_without_update(self):

        status, body = self.post("/api/run?update=0", {"X-App-Action": "1"})
        self.assertEqual(status, 202)
        self.assertTrue(body["started"])

        for _ in range(100):
            state = json.loads(self.get("/api/status")[1])
            if not state["busy"]:
                break
            time.sleep(0.1)
        self.assertFalse(state["busy"])
        self.assertIn("STEP 3/3  Paper trading", state["log"])
        self.assertEqual(state["log"][-1], "Done.")


if __name__ == "__main__":
    unittest.main()


class TestExtraPaperAccounts(unittest.TestCase):

    def test_routine_runs_every_account_and_the_overview_lists_them(self):
        from src.app.overview_page import overview_page
        from src.app.routine import daily_routine
        from src.paper_trading.accounts import EXTRA_ACCOUNTS, ExtraAccount
        from src.reporting.dashboard import exchange_status

        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            repository = make_repository(folder)
            main = PaperTradingStore(folder / "paper.db")
            extras = [
                (ExtraAccount(a.id, a.strategy_id, a.filename, a.starting_cash, START), PaperTradingStore(folder / a.filename))
                for a in EXTRA_ACCOUNTS
            ]
            now = START + timedelta(hours=HOURS)
            log = []
            with patch("src.app.routine.datetime") as fake, patch("src.paper_trading.trader.datetime") as fake2:
                for f in (fake, fake2):
                    f.now.return_value = now
                    f.side_effect = lambda *a, **k: datetime(*a, **k)
                history = daily_routine(repository, main, update=False, log=log.append, extra_accounts=extras)

            for config, store in extras:
                account = store.get_account()
                self.assertIsNotNone(account, config.id)
                self.assertEqual(account.starting_cash, 3500.0)
                self.assertTrue(store.decisions())
            self.assertTrue(any("Paper account 'lab'" in line for line in log))

            page = overview_page(history, exchange_status(repository, now), main.get_account(), False,
                                 [(c.definition.name, s.get_account()) for c, s in extras])
            self.assertIn("Side by side", page)
            self.assertIn("Lab: weekly MACD", page)
