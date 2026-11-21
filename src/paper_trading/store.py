"""
Storage for the paper-trading account, in its own SQLite file
(database/paper_trading.db by default), separate from the market data.

Decisions and fills are append-only: they are written once and never
changed afterwards, so the log always shows exactly what the system
decided at the time, with what it knew then.
"""

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = PROJECT_ROOT / "database" / "paper_trading.db"


@dataclass(frozen=True)
class Account:
    created_at: datetime
    strategy: str
    timeframe: str
    starting_cash: float
    start_candle: datetime  # first candle the account may act on
    cash: float
    btc: float
    last_processed: datetime | None  # last candle a decision was made for
    pending_side: str | None  # "buy" / "sell" waiting for a fill
    pending_decision_id: int | None
    entry_price: float | None
    stop_price: float | None


@dataclass(frozen=True)
class Decision:
    id: int
    candle_time: datetime
    recorded_at: datetime
    action: str  # BUY, SELL, HOLD, WAIT, SKIP
    reason: str
    close: float
    snapshot: dict


@dataclass(frozen=True)
class Fill:
    id: int
    decision_id: int
    filled_at: datetime
    side: str
    price: float  # after slippage
    fee: float  # in USD
    btc: float
    cash_after: float
    btc_after: float


def _ts(value: datetime | None) -> str | None:
    return None if value is None else value.astimezone(timezone.utc).isoformat()


def _dt(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


class PaperTradingStore:

    def __init__(self, path: str | Path = DEFAULT_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS account (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    created_at TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    starting_cash REAL NOT NULL,
                    start_candle TEXT NOT NULL,
                    cash REAL NOT NULL,
                    btc REAL NOT NULL,
                    last_processed TEXT,
                    pending_side TEXT,
                    pending_decision_id INTEGER,
                    entry_price REAL,
                    stop_price REAL
                );
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candle_time TEXT NOT NULL UNIQUE,
                    recorded_at TEXT NOT NULL,
                    action TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    close REAL NOT NULL,
                    snapshot TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS fills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    decision_id INTEGER NOT NULL REFERENCES decisions(id),
                    filled_at TEXT NOT NULL,
                    side TEXT NOT NULL,
                    price REAL NOT NULL,
                    fee REAL NOT NULL,
                    btc REAL NOT NULL,
                    cash_after REAL NOT NULL,
                    btc_after REAL NOT NULL
                );
            """)

    # -- account -------------------------------------------------------------

    def create_account(
        self, strategy: str, timeframe: str, starting_cash: float, start_candle: datetime
    ) -> Account:
        if self.get_account() is not None:
            raise RuntimeError(
                "A paper account already exists. Use reset_account first."
            )
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "INSERT INTO account (id, created_at, strategy, timeframe, "
                "starting_cash, start_candle, cash, btc) VALUES (1, ?, ?, ?, ?, ?, ?, 0)",
                (_ts(datetime.now(timezone.utc)), strategy, timeframe,
                 starting_cash, _ts(start_candle), starting_cash),
            )
        return self.get_account()

    def get_account(self) -> Account | None:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute(
                "SELECT created_at, strategy, timeframe, starting_cash, start_candle, "
                "cash, btc, last_processed, pending_side, pending_decision_id, "
                "entry_price, stop_price FROM account WHERE id = 1"
            ).fetchone()
        if row is None:
            return None
        return Account(
            _dt(row[0]), row[1], row[2], row[3], _dt(row[4]), row[5], row[6],
            _dt(row[7]), row[8], row[9], row[10], row[11],
        )

    def update_account(self, **fields) -> None:
        allowed = {"cash", "btc", "last_processed", "pending_side",
                   "pending_decision_id", "entry_price", "stop_price"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unknown account fields: {unknown}")
        values = [
            _ts(v) if isinstance(v, datetime) else v for v in fields.values()
        ]
        assignments = ", ".join(f"{name} = ?" for name in fields)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(f"UPDATE account SET {assignments} WHERE id = 1", values)

    def reset_account(self) -> None:
        """Delete the account and its whole history (asks nothing: callers confirm)."""
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.executescript(
                "DELETE FROM fills; DELETE FROM decisions; DELETE FROM account;"
            )

    # -- append-only log -----------------------------------------------------

    def add_decision(
        self, candle_time: datetime, action: str, reason: str, close: float, snapshot: dict
    ) -> int:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            cursor = connection.execute(
                "INSERT INTO decisions (candle_time, recorded_at, action, reason, close, snapshot) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (_ts(candle_time), _ts(datetime.now(timezone.utc)), action, reason,
                 close, json.dumps(snapshot)),
            )
            return cursor.lastrowid

    def add_fill(
        self, decision_id: int, filled_at: datetime, side: str, price: float,
        fee: float, btc: float, cash_after: float, btc_after: float,
    ) -> None:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "INSERT INTO fills (decision_id, filled_at, side, price, fee, btc, "
                "cash_after, btc_after) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (decision_id, _ts(filled_at), side, price, fee, btc, cash_after, btc_after),
            )

    def decisions(self, limit: int | None = None) -> list[Decision]:
        query = (
            "SELECT id, candle_time, recorded_at, action, reason, close, snapshot "
            "FROM decisions ORDER BY candle_time DESC"
        )
        if limit:
            query += f" LIMIT {int(limit)}"
        with closing(sqlite3.connect(self.path)) as connection:
            rows = connection.execute(query).fetchall()
        return [
            Decision(r[0], _dt(r[1]), _dt(r[2]), r[3], r[4], r[5], json.loads(r[6]))
            for r in rows
        ]

    def fills(self) -> list[Fill]:
        with closing(sqlite3.connect(self.path)) as connection:
            rows = connection.execute(
                "SELECT id, decision_id, filled_at, side, price, fee, btc, cash_after, "
                "btc_after FROM fills ORDER BY filled_at"
            ).fetchall()
        return [Fill(r[0], r[1], _dt(r[2]), r[3], r[4], r[5], r[6], r[7], r[8]) for r in rows]
