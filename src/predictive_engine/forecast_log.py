"""
Forecast log (predictive engine, phase 4): every scenario forecast is stored
when it is made and never changed (database/predictions.db, separate from the
market and paper-trading files). Once its outcome is decided (the target or
stop was reached, or the horizon passed), the outcome is added in a separate
table, so the log shows over time how good the forecasts really were.

One forecast per daily candle and model version: recording the same candle
again does nothing (the first one stays).
"""

import json
import math
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from src.data_collection.market_data import MarketData


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = PROJECT_ROOT / "database" / "predictions.db"


class ForecastLog:

    def __init__(self, path: str | Path = DEFAULT_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS forecasts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at TEXT NOT NULL,
                    candle_time TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    close REAL NOT NULL,
                    horizon_days INTEGER NOT NULL,
                    target REAL NOT NULL,
                    stop REAL NOT NULL,
                    p_bull REAL NOT NULL,
                    p_bear REAL NOT NULL,
                    p_range REAL NOT NULL,
                    cases INTEGER NOT NULL,
                    details TEXT NOT NULL,
                    UNIQUE (candle_time, model_version)
                );
                CREATE TABLE IF NOT EXISTS outcomes (
                    forecast_id INTEGER PRIMARY KEY REFERENCES forecasts(id),
                    kind TEXT NOT NULL,
                    decided_candle TEXT NOT NULL,
                    scored_at TEXT NOT NULL
                );
            """)

    def record(self, scenarios: dict) -> bool:
        """Store a forecast (Scenarios.as_dict()). False if this candle was already recorded."""
        p = {s["kind"]: s["probability"] for s in scenarios["scenarios"]}
        with closing(sqlite3.connect(self.path)) as connection, connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO forecasts (recorded_at, candle_time, model_version, close, horizon_days,"
                " target, stop, p_bull, p_bear, p_range, cases, details) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (datetime.now(timezone.utc).isoformat(timespec="seconds"), scenarios["candle_time"],
                 scenarios["model_version"], scenarios["close"], scenarios["horizon_days"], scenarios["target"],
                 scenarios["stop"], p["bull"], p["bear"], p["range"], scenarios["cases"], json.dumps(scenarios)),
            )
            return cursor.rowcount == 1

    def score_pending(self, daily_candles: list[MarketData]) -> int:
        """Add outcomes for forecasts that are now decided. Returns how many were added."""
        by_time = {c.timestamp.isoformat(): i for i, c in enumerate(daily_candles)}
        added = 0
        with closing(sqlite3.connect(self.path)) as connection, connection:
            rows = connection.execute(
                "SELECT f.id, f.candle_time, f.target, f.stop, f.horizon_days FROM forecasts f "
                "LEFT JOIN outcomes o ON o.forecast_id = f.id WHERE o.forecast_id IS NULL"
            ).fetchall()
            for fid, candle_time, target, stop, horizon in rows:
                i = by_time.get(candle_time)
                if i is None:
                    continue
                kind = decided = None
                for j in range(i + 1, min(i + horizon, len(daily_candles) - 1) + 1):
                    x = daily_candles[j].close
                    if x >= target:
                        kind, decided = "bull", j
                        break
                    if x <= stop:
                        kind, decided = "bear", j
                        break
                if kind is None and i + horizon <= len(daily_candles) - 1:
                    kind, decided = "range", i + horizon
                if kind is None:
                    continue  # still open
                connection.execute(
                    "INSERT OR IGNORE INTO outcomes VALUES (?, ?, ?, ?)",
                    (fid, kind, daily_candles[decided].timestamp.isoformat(),
                     datetime.now(timezone.utc).isoformat(timespec="seconds")),
                )
                added += 1
        return added

    def history(self, limit: int = 60) -> list[dict]:
        with closing(sqlite3.connect(self.path)) as connection:
            rows = connection.execute(
                "SELECT f.candle_time, f.model_version, f.close, f.target, f.stop, f.p_bull, f.p_bear, f.p_range,"
                " f.cases, o.kind, o.decided_candle FROM forecasts f LEFT JOIN outcomes o ON o.forecast_id = f.id"
                " ORDER BY f.candle_time DESC LIMIT ?", (limit,),
            ).fetchall()
        keys = ("candle_time", "model_version", "close", "target", "stop", "p_bull", "p_bear", "p_range",
                "cases", "outcome", "decided_candle")
        return [dict(zip(keys, r)) for r in rows]

    def track_record(self) -> dict:
        """How the logged forecasts did so far: count, Brier score, hit rate of the top scenario."""
        with closing(sqlite3.connect(self.path)) as connection:
            rows = connection.execute(
                "SELECT f.p_bull, f.p_bear, f.p_range, o.kind FROM forecasts f JOIN outcomes o ON o.forecast_id = f.id"
            ).fetchall()
        if not rows:
            return {"scored": 0}
        brier = top_hits = ll = 0.0
        for pb, pd, pr, kind in rows:
            p = {"bull": pb, "bear": pd, "range": pr}
            brier += sum((p[k] - (k == kind)) ** 2 for k in p)
            ll -= math.log(max(p[kind], 1e-6))
            top_hits += max(p, key=p.get) == kind
        n = len(rows)
        return {"scored": n, "brier": round(brier / n, 4), "log_loss": round(ll / n, 4),
                "top_scenario_hit_rate": round(top_hits / n, 3)}
