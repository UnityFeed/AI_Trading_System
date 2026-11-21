"""
The local app: a small web server on your own computer (127.0.0.1 only,
not reachable from other machines) that serves

  /              the overview dashboard
  /chart         the interactive chart (all timeframes and indicators)
  /api/chart     chart data in chunks (used by the chart page)
  /api/status    progress of a running job
  /api/run       POST: start the daily routine (update data + paper trader)

Buttons only work from the app's own pages: every POST must carry the
header X-App-Action, which other websites cannot send to this server.
"""

import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from src.app.chart_data import build_series, chunk, trade_markers
from src.app.chart_page import NAV_CSS, NAV_SCRIPT, chart_page, nav_html
from src.app.strategy_page import strategy_page
from src.backtesting.engine import CostSettings, MarginSettings
from src.backtesting.market import build_market
from src.backtesting.report import strategy_report, trade_markers_from_report
from src.strategies.registry import ACTIVE_STRATEGY_ID, STRATEGIES, get_strategy
from src.analysis.technical_indicators import indicator_tables
from src.app.routine import daily_routine, load_history
from src.data_collection.market_data_repository import MarketDataRepository
from src.paper_trading.store import PaperTradingStore
from src.reporting.dashboard import gather, render


TIMEFRAMES = ("1h", "4h", "1d")
FEES = (0.80, 0.40)
LEVERAGES = (1.0, 2.0, 3.0, 5.0, 10.0)  # Kraken allows up to 20x on BTC/USD
MAX_CHUNK = 5000


class AppState:

    def __init__(self, repository: MarketDataRepository, store: PaperTradingStore):
        self.repository = repository
        self.store = store
        self.job_lock = threading.Lock()
        self.data_lock = threading.Lock()
        self.busy = False
        self.log: list[str] = []
        self.last_job: str | None = None
        self.reload()

    # -- data ------------------------------------------------------------------

    def reload(self) -> None:
        """Rebuild everything shown in the app from the databases."""
        history = load_history(self.repository)
        tables = indicator_tables(history.candles, TIMEFRAMES)
        series = {tf: build_series(history, tf, tables[tf]) for tf in TIMEFRAMES}
        dashboard = render(
            gather(self.repository, history, self.store, tables=tables),
            nav_html=f"<style>{NAV_CSS}</style>{nav_html('overview')}<script>{NAV_SCRIPT}</script>",
        )
        with self.data_lock:
            self.history = history
            self.series = series
            self.dashboard = dashboard
            self.tables = tables
            self.markets = {}
            self.reports = {}

    def report(self, strategy_id: str, fee_pct: float, leverage: float = 1.0) -> dict:
        """Full-history backtest report, cached until the next data reload."""
        key = (strategy_id, fee_pct, leverage)
        with self.data_lock:
            if key in self.reports:
                return self.reports[key]
            definition = get_strategy(strategy_id)
            market = self.markets.get(definition.timeframe)
            if market is None:
                market = self.markets[definition.timeframe] = build_market(
                    self.history, definition.timeframe, table=self.tables.get(definition.timeframe)
                )
            report = strategy_report(
                market, definition, CostSettings(fee_pct=fee_pct), MarginSettings(leverage=leverage)
            )
            self.reports[key] = report
            return report

    # -- jobs ------------------------------------------------------------------

    def start_daily_routine(self, update: bool) -> bool:
        with self.job_lock:
            if self.busy:
                return False
            self.busy = True
            self.log = []
        threading.Thread(target=self._run, args=(update,), daemon=True).start()
        return True

    def _write(self, *parts) -> None:
        self.log.append(" ".join(str(p) for p in parts))

    def _run(self, update: bool) -> None:
        try:
            daily_routine(self.repository, self.store, update=update, log=self._write)
            self._write("Refreshing charts and overview...")
            self.reload()
            self._write("Done.")
            self.last_job = f"finished {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC"
        except Exception as exc:  # shown in the app instead of crashing the server
            self._write(f"ERROR: {exc}")
            self.last_job = "failed"
        finally:
            self.busy = False


def make_handler(state: AppState):

    class Handler(BaseHTTPRequestHandler):

        def log_message(self, format, *args):  # keep the terminal quiet
            pass

        def _send(self, status: int, body: str | bytes, content_type: str) -> None:
            data = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _json(self, payload, status: int = 200) -> None:
            self._send(status, json.dumps(payload, separators=(",", ":")), "application/json")

        def do_GET(self):
            url = urlparse(self.path)
            query = parse_qs(url.query)

            if url.path == "/":
                with state.data_lock:
                    page = state.dashboard
                return self._send(200, page, "text/html; charset=utf-8")

            if url.path == "/chart":
                return self._send(200, chart_page(), "text/html; charset=utf-8")

            if url.path == "/strategy":
                return self._send(200, strategy_page(), "text/html; charset=utf-8")

            if url.path == "/api/strategies":
                return self._json({
                    "active": ACTIVE_STRATEGY_ID,
                    "fees": FEES,
                    "leverages": LEVERAGES,
                    "strategies": [
                        {"id": s.id, "name": s.name, "timeframe": s.timeframe, "rules": s.spec.name,
                         "description": s.description, "origin": s.origin}
                        for s in STRATEGIES
                    ],
                })

            if url.path == "/api/backtest":
                strategy_id = query.get("strategy", [ACTIVE_STRATEGY_ID])[0]
                try:
                    fee = float(query.get("fee", [FEES[0]])[0])
                    leverage = float(query.get("leverage", ["1"])[0])
                    get_strategy(strategy_id)
                except (KeyError, ValueError):
                    return self._json({"error": "unknown strategy or bad fee"}, 400)
                if fee not in FEES or leverage not in LEVERAGES:
                    return self._json({"error": f"fee must be one of {FEES}, leverage one of {LEVERAGES}"}, 400)
                return self._json(state.report(strategy_id, fee, leverage))

            if url.path == "/api/chart":
                timeframe = query.get("tf", ["1d"])[0]
                if timeframe not in TIMEFRAMES:
                    return self._json({"error": "unknown timeframe"}, 400)
                try:
                    before = int(query["before"][0]) if "before" in query else None
                    limit = min(int(query.get("limit", [3000])[0]), MAX_CHUNK)
                except ValueError:
                    return self._json({"error": "bad number"}, 400)
                with state.data_lock:
                    payload = chunk(state.series[timeframe], before, limit)
                source = query.get("trades", ["paper"])[0]
                if source == "paper":
                    payload["markers"] = trade_markers(state.store.fills(), timeframe)
                elif source == "none":
                    payload["markers"] = []
                else:
                    try:
                        report = state.report(source, FEES[0])
                    except KeyError:
                        return self._json({"error": "unknown strategy"}, 400)
                    payload["markers"] = trade_markers_from_report(report, timeframe)
                return self._json(payload)

            if url.path == "/api/status":
                return self._json({"busy": state.busy, "log": state.log[-200:], "last_job": state.last_job})

            return self._send(404, "Not found", "text/plain; charset=utf-8")

        def do_POST(self):
            url = urlparse(self.path)
            if self.headers.get("X-App-Action") != "1":
                return self._json({"error": "missing X-App-Action header"}, 403)
            if url.path == "/api/run":
                update = parse_qs(url.query).get("update", ["1"])[0] == "1"
                started = state.start_daily_routine(update)
                return self._json({"started": started}, 202 if started else 409)
            return self._json({"error": "not found"}, 404)

    return Handler


def serve(state: AppState, port: int = 8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(state))
