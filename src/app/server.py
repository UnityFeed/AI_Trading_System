"""
The local app: a small web server on your own computer (127.0.0.1 only,
not reachable from other machines) that serves

  /              the overview: the selected strategy's latest trade and signal
  /chart         the interactive chart (all timeframes, indicators, the
                 selected strategy's trades and current state)
  /strategy      the strategy tester (full-history backtest)
  /api/chart     chart data in chunks (used by the chart page)
  /api/strategies, /api/backtest, /api/strategy-state   strategy data
  /api/compare   key numbers of every strategy side by side
  /api/structure market structure of a timeframe (predictive engine, phase 1)
  /api/scenarios today's (or ?date=) bull / bear / range scenarios, ?h=7|14|30 (learning engine)
  /api/tools     chart tools as known at ?until=: zones, Fibonacci, patterns, regime, volume profile
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
from src.app.chart_page import chart_page
from src.app.overview_page import overview_page
from src.app.strategy_page import strategy_page
from src.backtesting.engine import CostSettings, MarginSettings
from src.backtesting.exposure import MissingExternalData
from src.backtesting.market import build_market
from src.predictive_engine import learner, training
from src.predictive_engine.forecast_log import ForecastLog
from src.predictive_engine.service import EngineService
from src.predictive_engine.structure import analyse as analyse_structure
from src.backtesting.report import start_years, strategy_report, strategy_state, trade_markers_from_report
from src.strategies.registry import ACTIVE_STRATEGY_ID, STRATEGIES, get_strategy
from src.analysis.technical_indicators import indicator_tables
from src.app.routine import daily_routine, load_history
from src.data_collection.external_data import ExternalDataStore
from src.data_collection.market_data_repository import MarketDataRepository
from src.paper_trading.store import PaperTradingStore
from src.paper_trading.trader import KILL_SWITCH
from src.reporting.dashboard import exchange_status


TIMEFRAMES = ("1h", "4h", "1d", "1w")
FEES = (0.25, 0.80, 0.40)  # first = default (Bybit EU, the owner's exchange)
FEE_LABELS = {
    0.25: "Bybit EU (your account)",
    0.80: "Kraken market orders",
    0.40: "Kraken limit orders",
}
LEVERAGES = (1.0, 2.0, 3.0, 5.0, 10.0)  # Kraken allows up to 20x on BTC/USD
MAX_CHUNK = 5000


class AppState:

    def __init__(self, repository: MarketDataRepository, store: PaperTradingStore,
                 external_store: ExternalDataStore | None = None, extra_accounts=(),
                 forecast_log: ForecastLog | None = None):
        self.repository = repository
        self.store = store
        self.extra_accounts = list(extra_accounts)  # (ExtraAccount, PaperTradingStore)
        self.forecast_log = forecast_log  # predictive engine: forecasts are recorded here (None = not recorded)

        self.external_store = external_store
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
        exchanges = exchange_status(self.repository, datetime.now(timezone.utc))
        external = self.external_store.load_all() if self.external_store else {}
        with self.data_lock:
            self.external = external
            self.history = history
            self.series = series
            self.exchanges = exchanges
            self.tables = tables
            self.markets = {}
            self.reports = {}
            self.states = {}
            self.structures = {}
            self.engine = None  # predictive engine (learning replay), built on first use

    def _market(self, timeframe: str):
        """Backtest market for one timeframe (call with data_lock held)."""
        market = self.markets.get(timeframe)
        if market is None:
            market = self.markets[timeframe] = build_market(
                self.history, timeframe, table=self.tables.get(timeframe), external=self.external
            )
        return market

    def state(self, strategy_id: str) -> dict:
        """Where a strategy stands now, cached until the next data reload."""
        with self.data_lock:
            if strategy_id not in self.states:
                definition = get_strategy(strategy_id)
                self.states[strategy_id] = strategy_state(self._market(definition.timeframe), definition)
            return self.states[strategy_id]

    def structure(self, timeframe: str) -> dict:
        """Market structure of one timeframe (swings, events, trend now), cached until reload."""
        with self.data_lock:
            if timeframe not in self.structures:
                candles = self.tables[timeframe][0]
                s = analyse_structure(candles, timeframe)
                self.structures[timeframe] = {
                    "timeframe": timeframe,
                    "trend": s.trend[-1] if s.trend else "none",
                    "swing_high": s.swing_high[-1] if s.swing_high else None,
                    "swing_low": s.swing_low[-1] if s.swing_low else None,
                    "pivots": [
                        {"time": int(p.time.timestamp()), "price": p.price, "kind": p.kind, "label": p.label,
                         "confirmed": p.confirmed_time.isoformat()}
                        for p in s.pivots
                    ],
                    "events": [
                        {"time": int(candles[e.index].timestamp.timestamp()), "kind": e.kind,
                         "direction": e.direction, "level": e.level}
                        for e in s.events
                    ],
                }
            return self.structures[timeframe]

    def _engine(self) -> EngineService:
        """The predictive engine for the current data (call with data_lock held)."""
        if self.engine is None:
            markets = {tf: self._market(tf) for tf in ("1h", "4h", "1d", "1w")}
            self.engine = EngineService(markets["1d"], self.history.candles, markets=markets, cache=training.load())
        return self.engine

    def scenario_state(self, horizon: int = 30, day: datetime | None = None, timeframe: str = "1d") -> dict:
        """The learning engine's scenarios at the latest close (logged once per candle) or as made on a past day."""
        with self.data_lock:
            engine = self._engine()
            if not engine.ready(timeframe):
                if timeframe in engine.errors:
                    return {"error": f"the {timeframe} learner failed: {engine.errors[timeframe]}"}
                engine.prepare_in_background(timeframe)  # 1h/4h: replay the whole chart once (up to ~2 minutes)
                return {"status": "learning", "timeframe": timeframe,
                        "message": f"The {timeframe} AI is getting ready: seconds with a training session, up to a few "
                                   "minutes without one (python -m scripts.train_engine)."}
            payload = engine.scenarios(horizon, day, timeframe)
            payload["learning_curve"] = engine.curve(horizon, timeframe)
            candles = engine.markets[timeframe].candles
        if day is None and self.forecast_log is not None and "scenarios" in payload:
            self.forecast_log.record(payload)
            self.forecast_log.score_pending(candles, timeframe)
            payload["track_record"] = self.forecast_log.track_record(payload["model_version"])
        return payload

    def tools(self, timeframe: str, until: datetime | None = None) -> dict:
        with self.data_lock:
            engine = self._engine()
            candles = self.tables[timeframe][0]
            return engine.tools(timeframe, candles, until)

    def overview(self) -> str:
        with self.data_lock:
            history, exchanges = self.history, self.exchanges
        extras = [(config.definition.name, store.get_account()) for config, store in self.extra_accounts]
        return overview_page(history, exchanges, self.store.get_account(), KILL_SWITCH.exists(), extras)

    def start_years(self) -> list[int]:
        """Years a test can start in: every full calendar year in the data."""
        with self.data_lock:
            candles = self.history.candles
        return start_years(candles[0].timestamp, candles[-1].timestamp) if candles else []

    def report(self, strategy_id: str, fee_pct: float, leverage: float = 1.0,
               start_year: int | None = None) -> dict:
        """Backtest report (full history or from 1 January of start_year), cached until the next reload."""
        key = (strategy_id, fee_pct, leverage, start_year)
        with self.data_lock:
            if key in self.reports:
                return self.reports[key]
            definition = get_strategy(strategy_id)
            market = self._market(definition.timeframe)
            start = None if start_year is None else datetime(start_year, 1, 1, tzinfo=timezone.utc)
            report = strategy_report(
                market, definition, CostSettings(fee_pct=fee_pct), MarginSettings(leverage=leverage), start
            )
            self.reports[key] = report
            return report

    def compare(self, fee_pct: float, start_year: int | None = None) -> dict:
        """Key numbers of every strategy with the same fee and start (no margin)."""
        rows, held = [], None
        for definition in STRATEGIES:
            try:
                report = self.report(definition.id, fee_pct, 1.0, start_year)
            except MissingExternalData as error:
                rows.append({"id": definition.id, "name": definition.name, "error": str(error)})
                continue
            summary, metrics = report["summary"], report["metrics"]
            starts = report["by_start_year"]
            held = held or {**report["buy_and_hold"], **report["buy_and_hold_metrics"]}
            rows.append({
                "id": definition.id, "name": definition.name, "kind": definition.kind,
                "total_return_pct": summary["total_return_pct"],
                "btc_vs_hold": summary["btc_vs_hold"],
                "max_drawdown_pct": summary["max_drawdown_pct"],
                "sharpe": metrics["sharpe"],
                "break_even_fee_pct": metrics["break_even_fee_pct"],
                "exposure_pct": summary["exposure_pct"],
                "start_years_ahead": sum(r["btc_vs_hold"] >= 1 for r in starts),
                "start_years": len(starts),
            })
        return {"rows": rows, "buy_and_hold": held}

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
            daily_routine(self.repository, self.store, update=update, log=self._write,
                          external_store=self.external_store, extra_accounts=self.extra_accounts)
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
                return self._send(200, state.overview(), "text/html; charset=utf-8")

            if url.path == "/api/strategy-state":
                try:
                    return self._json(state.state(query.get("strategy", [ACTIVE_STRATEGY_ID])[0]))
                except KeyError:
                    return self._json({"error": "unknown strategy"}, 400)
                except MissingExternalData as error:
                    return self._json({"error": str(error)}, 409)

            if url.path == "/chart":
                return self._send(200, chart_page(), "text/html; charset=utf-8")

            if url.path == "/strategy":
                return self._send(200, strategy_page(), "text/html; charset=utf-8")

            if url.path == "/api/strategies":
                return self._json({
                    "active": ACTIVE_STRATEGY_ID,
                    "fees": FEES,
                    "fee_labels": {str(f): FEE_LABELS[f] for f in FEES},
                    "leverages": LEVERAGES,
                    "start_years": state.start_years(),
                    "strategies": [
                        {"id": s.id, "name": s.name, "timeframe": s.timeframe, "rules": s.rules_text,
                         "description": s.description, "origin": s.origin, "kind": s.kind,
                         # graded strategies never borrow, so margin does not apply
                         "supports_margin": s.kind == "rules"}
                        for s in STRATEGIES
                    ],
                })

            if url.path == "/api/backtest":
                strategy_id = query.get("strategy", [ACTIVE_STRATEGY_ID])[0]
                try:
                    fee = float(query.get("fee", [FEES[0]])[0])
                    leverage = float(query.get("leverage", ["1"])[0])
                    start_text = query.get("start", ["all"])[0]
                    start_year = None if start_text == "all" else int(start_text)
                    get_strategy(strategy_id)
                except (KeyError, ValueError):
                    return self._json({"error": "unknown strategy or bad fee"}, 400)
                if fee not in FEES or leverage not in LEVERAGES:
                    return self._json({"error": f"fee must be one of {FEES}, leverage one of {LEVERAGES}"}, 400)
                if start_year is not None and start_year not in state.start_years():
                    return self._json({"error": f"start must be 'all' or one of {state.start_years()}"}, 400)
                try:
                    return self._json(state.report(strategy_id, fee, leverage, start_year))
                except MissingExternalData as error:
                    return self._json({"error": str(error)}, 409)

            if url.path in ("/api/scenarios", "/api/tools"):
                try:
                    until = query.get("date", query.get("until", [None]))[0]
                    day = None
                    if until:
                        day = (datetime.fromtimestamp(int(until), timezone.utc) if until.isdigit()
                               else datetime.fromisoformat(until).replace(tzinfo=timezone.utc))
                    timeframe = query.get("tf", ["1d"])[0]
                    if url.path == "/api/scenarios":
                        if timeframe not in learner.TF_HORIZONS:
                            raise ValueError
                        horizon = int(query.get("h", [str(learner.TF_HORIZONS[timeframe][-1])])[0])
                        if horizon not in learner.TF_HORIZONS[timeframe]:
                            raise ValueError
                        return self._json(state.scenario_state(horizon, day, timeframe))
                    if timeframe not in TIMEFRAMES:
                        raise ValueError
                    return self._json(state.tools(timeframe, day))
                except ValueError:
                    return self._json({"error": "bad horizon, timeframe or date"}, 400)

            if url.path == "/api/structure":
                timeframe = query.get("tf", ["1d"])[0]
                if timeframe not in TIMEFRAMES:
                    return self._json({"error": "unknown timeframe"}, 400)
                return self._json(state.structure(timeframe))

            if url.path == "/api/compare":
                try:
                    fee = float(query.get("fee", [FEES[0]])[0])
                    start_text = query.get("start", ["all"])[0]
                    start_year = None if start_text == "all" else int(start_text)
                except ValueError:
                    return self._json({"error": "bad fee or start"}, 400)
                if fee not in FEES or (start_year is not None and start_year not in state.start_years()):
                    return self._json({"error": "unknown fee or start year"}, 400)
                return self._json(state.compare(fee, start_year))

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
                    except MissingExternalData:
                        report = {"trades": [], "rebalances": []}
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
