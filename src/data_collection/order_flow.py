"""
Order flow and order book, recorded from Kraken's free public API, from
now on (there is no free history of order books; see
docs/research/2026-11-22_strategy_feasibility.md).

Two kinds of data, in their own SQLite file (database/order_flow.db):

1. trade_flow: per completed UTC hour, from every Kraken BTC/USD trade:
   buy volume (a buyer took an ask at once), sell volume (a seller hit a
   bid at once), their counts, and the exact VWAP (volume-weighted average
   price). Buy minus sell volume, added up over time, is the CVD
   (cumulative volume delta). Kraken keeps its full trade history, so this
   can also be filled backwards, but a day takes about 100-150 requests.

2. book_snapshots: the top 500 price levels of the order book, summarised
   each time a snapshot is taken: best bid/ask, spread, BTC waiting within
   0.5% and 1% of the mid price on each side, and their imbalance. Only
   while the recorder runs (scripts/record_order_flow.py).

Nothing here is used by a strategy yet: it is collected so that it exists
when there is enough of it to test.
"""

import json
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from src.data_collection.kraken_trades_provider import KrakenTradesProvider


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = PROJECT_ROOT / "database" / "order_flow.db"
DEPTH_URL = "https://api.kraken.com/0/public/Depth?pair=XBTUSD&count=500"


@dataclass(frozen=True)
class HourFlow:
    hour: datetime
    buy_volume: float
    sell_volume: float
    buy_trades: int
    sell_trades: int
    vwap: float

    @property
    def delta(self) -> float:
        return self.buy_volume - self.sell_volume


def aggregate_trade_flow(trades: list[tuple[datetime, float, float, str]]) -> list[HourFlow]:
    """Trades (timestamp, price, volume, side 'b'/'s') -> one HourFlow per UTC hour with trades."""
    hours: dict[datetime, list] = {}
    for timestamp, price, volume, side in trades:
        hour = timestamp.replace(minute=0, second=0, microsecond=0)
        acc = hours.setdefault(hour, [0.0, 0.0, 0, 0, 0.0, 0.0])
        if side == "b":
            acc[0] += volume
            acc[2] += 1
        else:
            acc[1] += volume
            acc[3] += 1
        acc[4] += price * volume
        acc[5] += volume
    return [
        HourFlow(hour, a[0], a[1], a[2], a[3], a[4] / a[5] if a[5] > 0 else 0.0)
        for hour, a in sorted(hours.items())
    ]


def summarise_book(bids: list[tuple[float, float]], asks: list[tuple[float, float]]) -> dict:
    """bids/asks: (price, BTC) best first. Depth in BTC within 0.5% and 1% of the mid price."""
    best_bid, best_ask = bids[0][0], asks[0][0]
    mid = (best_bid + best_ask) / 2

    def depth(levels, limit, below):
        return sum(v for p, v in levels if (p >= limit if below else p <= limit))

    out = {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread_pct": (best_ask - best_bid) / mid * 100,
        # How far the 500 levels reach: depth beyond this is not seen.
        "bid_reach_pct": (mid - bids[-1][0]) / mid * 100,
        "ask_reach_pct": (asks[-1][0] - mid) / mid * 100,
    }
    for band, label in ((0.005, "05"), (0.01, "1")):
        bid = depth(bids, mid * (1 - band), below=True)
        ask = depth(asks, mid * (1 + band), below=False)
        out[f"bid_depth_{label}"] = bid
        out[f"ask_depth_{label}"] = ask
        out[f"imbalance_{label}"] = (bid - ask) / (bid + ask) if bid + ask > 0 else 0.0
    return out


def fetch_order_book() -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    request = Request(DEPTH_URL, headers={"User-Agent": "AI-Trading-System/1.0"})
    with urlopen(request, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
    if data.get("error"):
        raise RuntimeError(f"Kraken API error: {data['error']}")
    book = next(iter(data["result"].values()))
    bids = [(float(p), float(v)) for p, v, *_ in book["bids"]]
    asks = [(float(p), float(v)) for p, v, *_ in book["asks"]]
    return bids, asks


BOOK_FIELDS = (
    "best_bid", "best_ask", "spread_pct", "bid_reach_pct", "ask_reach_pct",
    "bid_depth_05", "ask_depth_05", "imbalance_05", "bid_depth_1", "ask_depth_1", "imbalance_1",
)


class OrderFlowStore:

    def __init__(self, path: str | Path = DEFAULT_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.executescript(f"""
                CREATE TABLE IF NOT EXISTS trade_flow (
                    hour TEXT PRIMARY KEY,
                    buy_volume REAL NOT NULL,
                    sell_volume REAL NOT NULL,
                    buy_trades INTEGER NOT NULL,
                    sell_trades INTEGER NOT NULL,
                    vwap REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS book_snapshots (
                    time TEXT PRIMARY KEY,
                    {", ".join(f"{name} REAL NOT NULL" for name in BOOK_FIELDS)}
                );
            """)

    def save_flow(self, flows: list[HourFlow]) -> int:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            before = connection.total_changes
            connection.executemany(
                "INSERT OR IGNORE INTO trade_flow VALUES (?, ?, ?, ?, ?, ?)",
                [(f.hour.isoformat(), f.buy_volume, f.sell_volume, f.buy_trades, f.sell_trades, f.vwap)
                 for f in flows],
            )
            return connection.total_changes - before

    def flows(self) -> list[HourFlow]:
        with closing(sqlite3.connect(self.path)) as connection:
            rows = connection.execute("SELECT * FROM trade_flow ORDER BY hour").fetchall()
        return [HourFlow(datetime.fromisoformat(r[0]), r[1], r[2], r[3], r[4], r[5]) for r in rows]

    def last_flow_hour(self) -> datetime | None:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute("SELECT MAX(hour) FROM trade_flow").fetchone()
        return datetime.fromisoformat(row[0]) if row and row[0] else None

    def save_book(self, when: datetime, summary: dict) -> None:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                f"INSERT OR IGNORE INTO book_snapshots VALUES (?, {', '.join('?' for _ in BOOK_FIELDS)})",
                (when.isoformat(timespec="seconds"), *(summary[name] for name in BOOK_FIELDS)),
            )

    def book_count(self) -> int:
        with closing(sqlite3.connect(self.path)) as connection:
            return connection.execute("SELECT COUNT(*) FROM book_snapshots").fetchone()[0]


def collect_trade_flow(
    store: OrderFlowStore,
    provider=None,
    now: datetime | None = None,
    first_start: timedelta = timedelta(days=7),
    max_hours: int = 24,
    log=print,
) -> int:
    """
    Fill trade_flow forward with completed hours, from the hour after the
    last stored one (first run: `first_start` ago), at most `max_hours` per
    call. Hours without any trade get no row. Returns the rows saved.
    """
    provider = provider or KrakenTradesProvider()
    now = now or datetime.now(timezone.utc)
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    last = store.last_flow_hour()
    start = last + timedelta(hours=1) if last else current_hour - first_start
    end = min(current_hour, start + timedelta(hours=max_hours))
    if start >= end:
        return 0
    trades = provider.fetch_trades_with_side(start, end)
    flows = aggregate_trade_flow(trades)
    saved = store.save_flow(flows)
    log(f"  trade flow {start:%Y-%m-%d %H:%M} to {end:%Y-%m-%d %H:%M} UTC: "
        f"{len(trades):,} trades, {saved} hours saved")
    return saved


def record_book(store: OrderFlowStore, now: datetime | None = None, fetch=fetch_order_book) -> dict:
    bids, asks = fetch()
    summary = summarise_book(bids, asks)
    store.save_book(now or datetime.now(timezone.utc), summary)
    return summary


def run_recorder(store: OrderFlowStore, book_every: int = 60, flow_every: int = 900, log=print) -> None:
    """Loop until stopped (Ctrl+C): a book snapshot every `book_every` seconds,
    trade flow caught up every `flow_every` seconds. Errors are logged, then retried."""
    next_flow = 0.0
    while True:
        started = time.time()
        try:
            summary = record_book(store)
            log(f"{datetime.now(timezone.utc):%H:%M:%S} book: spread {summary['spread_pct']:.4f}%, "
                f"within 1%: bids {summary['bid_depth_1']:.1f} BTC / asks {summary['ask_depth_1']:.1f} BTC")
        except Exception as error:
            log(f"book snapshot failed: {error}")
        if started >= next_flow:
            try:
                while collect_trade_flow(store, log=log) > 0:
                    pass  # catch up in steps of a day
            except Exception as error:
                log(f"trade flow failed: {error}")
            next_flow = started + flow_every
        time.sleep(max(1.0, book_every - (time.time() - started)))
