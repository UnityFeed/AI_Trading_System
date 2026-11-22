"""
Free external daily data (roadmap 9d): Bitcoin valuation and network data
from the Coin Metrics community API (free, no key):

  mvrv            CapMVRVCur     market value / realized value
  market_cap_usd  CapMrktCurUSD  market capitalisation in USD
  hash_rate       HashRate       estimated network hash rate (TH/s, 7-day)

Stored in its own SQLite file (database/external_data.db), never in the
market database.

Point-in-time rule: a value is stored the first time we see it and never
overwritten. If a later download reports a different value for the same
day (vendors revise on-chain numbers), the difference is written to the
`revisions` table, not applied. So from the first download on, the
history shows what was known at the time. Everything before the first
download is the vendor's present-day view of the past, which may contain
revisions (an honest limitation; strategies use these numbers with a 1-2
day delay and only in coarse buckets for this reason).
"""

import json
import sqlite3
import time
from collections.abc import Callable
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = PROJECT_ROOT / "database" / "external_data.db"

COINMETRICS_URL = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
SERIES = {
    "mvrv": "CapMVRVCur",
    "market_cap_usd": "CapMrktCurUSD",
    "hash_rate": "HashRate",
}


class ExternalDataStore:

    def __init__(self, path: str | Path = DEFAULT_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS observations (
                    series TEXT NOT NULL,
                    day TEXT NOT NULL,
                    value REAL NOT NULL,
                    first_seen TEXT NOT NULL,
                    PRIMARY KEY (series, day)
                );
                CREATE TABLE IF NOT EXISTS revisions (
                    series TEXT NOT NULL,
                    day TEXT NOT NULL,
                    stored_value REAL NOT NULL,
                    new_value REAL NOT NULL,
                    seen_at TEXT NOT NULL
                );
            """)

    def save(self, series: str, values: dict[date, float], seen_at: datetime | None = None) -> tuple[int, int]:
        """Store new days; log (never apply) changed values. Returns (new, revised)."""
        seen = (seen_at or datetime.now(timezone.utc)).isoformat(timespec="seconds")
        stored = self.load(series)
        new = revised = 0
        with closing(sqlite3.connect(self.path)) as connection, connection:
            for day, value in sorted(values.items()):
                old = stored.get(day)
                if old is None:
                    connection.execute(
                        "INSERT INTO observations (series, day, value, first_seen) VALUES (?, ?, ?, ?)",
                        (series, day.isoformat(), value, seen),
                    )
                    new += 1
                elif abs(old - value) > 1e-9 * max(1.0, abs(old)):
                    connection.execute(
                        "INSERT INTO revisions (series, day, stored_value, new_value, seen_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (series, day.isoformat(), old, value, seen),
                    )
                    revised += 1
        return new, revised

    def load(self, series: str) -> dict[date, float]:
        with closing(sqlite3.connect(self.path)) as connection:
            rows = connection.execute(
                "SELECT day, value FROM observations WHERE series = ? ORDER BY day", (series,)
            ).fetchall()
        return {date.fromisoformat(day): value for day, value in rows}

    def load_all(self) -> dict[str, dict[date, float]]:
        return {name: self.load(name) for name in SERIES}

    def latest_day(self, series: str) -> date | None:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute(
                "SELECT MAX(day) FROM observations WHERE series = ?", (series,)
            ).fetchone()
        return date.fromisoformat(row[0]) if row and row[0] else None


def _get_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "AI-Trading-System/1.0"})
    for attempt in range(4):
        try:
            with urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception:
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))
    raise RuntimeError("unreachable")


def fetch_coinmetrics(start: date | None = None) -> dict[str, dict[date, float]]:
    """All SERIES from `start` (default: full history), following next pages."""
    params = {
        "assets": "btc",
        "metrics": ",".join(SERIES.values()),
        "frequency": "1d",
        "page_size": 10000,
        "paging_from": "start",
        "start_time": (start or date(2010, 1, 1)).isoformat(),
    }
    url = f"{COINMETRICS_URL}?{urlencode(params)}"
    out: dict[str, dict[date, float]] = {name: {} for name in SERIES}
    while url:
        payload = _get_json(url)
        for row in payload.get("data", []):
            day = date.fromisoformat(row["time"][:10])
            for name, metric in SERIES.items():
                value = row.get(metric)
                if value is not None:
                    out[name][day] = float(value)
        url = payload.get("next_page_url")
    return out


def update_external_data(
    store: ExternalDataStore,
    log: Callable[..., None] = print,
    fetch: Callable[[date | None], dict[str, dict[date, float]]] = fetch_coinmetrics,
) -> dict[str, tuple[int, int]]:
    """
    Download what is new (plus the last 7 days, to notice revisions) and
    store it. Returns {series: (new days, revised days)}.
    """
    latest = [store.latest_day(name) for name in SERIES]
    start = None
    if all(latest):
        start = date.fromordinal(min(latest).toordinal() - 7)
    data = fetch(start)
    results = {}
    for name, values in data.items():
        new, revised = store.save(name, values)
        results[name] = (new, revised)
        last = store.latest_day(name)
        log(f"  {name:<15} {new:>5} new days, {revised} revised (kept the first value); latest {last}")
    return results
