"""
Other markets (owner, 24 Nov 2026): S&P 500, Nasdaq 100 ("NAS100"), Dow
Jones 30 ("US30"), gold and silver, daily. First as extra inputs for the AI
(how BTC's surroundings behave); trading them may come later.

Source: Yahoo Finance's public chart API (no key; long daily history:
S&P 500 from 1970, Nasdaq 100 from 1985, Dow from 1992, gold and silver
futures from 2000). It is NOT an official, documented API (Yahoo may change
or limit it; personal use only). Indices are the cash indices (^GSPC, ^NDX,
^DJI); gold and silver are the front-month COMEX futures (GC=F, SI=F), whose
roll from one contract to the next can cause small jumps.

Stored in its own SQLite file (database/other_markets.db), never in the
market database. Point-in-time rule as for the Coin Metrics data: a day's
bar is stored the first time it is seen and never overwritten; later
differences go to a `revisions` table. Each bar is labelled with its trading
DATE in the market's own time zone. The bar of the current trading date is
never stored (it may still be forming).

When may BTC use it? A bar dated D is complete by ~22:00 UTC on D (US close
16:00-17:00 New York). The AI uses it only from the close of BTC's daily
candle D (00:00 UTC on D+1) on, via the same rule as the other external data
(`backtesting.exposure._lookup` with no extra lag).
"""

import json
import sqlite3
import time
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = PROJECT_ROOT / "database" / "other_markets.db"
YAHOO_URL = "https://query2.finance.yahoo.com/v8/finance/chart/"

# our name -> (Yahoo symbol, description)
MARKETS = {
    "spx": ("^GSPC", "S&P 500"),
    "ndx": ("^NDX", "Nasdaq 100 (NAS100)"),
    "dji": ("^DJI", "Dow Jones 30 (US30)"),
    "gold": ("GC=F", "Gold (COMEX front-month future)"),
    "silver": ("SI=F", "Silver (COMEX front-month future)"),
}
REVISION_TOLERANCE = 1e-4  # relative close difference below this is not a revision


class OtherMarketsStore:

    def __init__(self, path: str | Path = DEFAULT_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS daily (
                    market TEXT NOT NULL,
                    day TEXT NOT NULL,
                    open REAL, high REAL, low REAL,
                    close REAL NOT NULL,
                    volume REAL,
                    source TEXT NOT NULL,
                    first_seen TEXT NOT NULL,
                    PRIMARY KEY (market, day)
                );
                CREATE TABLE IF NOT EXISTS revisions (
                    market TEXT NOT NULL,
                    day TEXT NOT NULL,
                    old_close REAL NOT NULL,
                    new_close REAL NOT NULL,
                    seen TEXT NOT NULL
                );
            """)

    def save(self, market: str, bars: list[dict], source: str = "yahoo") -> tuple[int, int]:
        """Store new days (first value kept). Returns (new days, revisions noted)."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        added = revised = 0
        with closing(sqlite3.connect(self.path)) as connection, connection:
            stored = dict(connection.execute("SELECT day, close FROM daily WHERE market = ?", (market,)))
            for b in bars:
                day = b["day"].isoformat()
                if day not in stored:
                    connection.execute("INSERT INTO daily VALUES (?,?,?,?,?,?,?,?,?)",
                                       (market, day, b.get("open"), b.get("high"), b.get("low"), b["close"],
                                        b.get("volume"), source, now))
                    added += 1
                elif abs(b["close"] / stored[day] - 1) > REVISION_TOLERANCE:
                    connection.execute("INSERT INTO revisions VALUES (?,?,?,?,?)",
                                       (market, day, stored[day], b["close"], now))
                    revised += 1
        return added, revised

    def closes(self, market: str) -> dict[date, float]:
        with closing(sqlite3.connect(self.path)) as connection:
            rows = connection.execute("SELECT day, close FROM daily WHERE market = ? ORDER BY day", (market,))
            return {date.fromisoformat(d): c for d, c in rows}

    def load_all(self) -> dict[str, dict[date, float]]:
        """Daily closes as external series named "mkt.<market>" (for Market.external)."""
        return {f"mkt.{m}": self.closes(m) for m in MARKETS if self.closes(m)}

    def latest_day(self, market: str) -> date | None:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute("SELECT MAX(day) FROM daily WHERE market = ?", (market,)).fetchone()
        return date.fromisoformat(row[0]) if row and row[0] else None


def fetch_yahoo(symbol: str, now: datetime | None = None, opener=urlopen) -> list[dict]:
    """Completed daily bars of one Yahoo symbol, oldest first, labelled by trading date in its own time zone."""
    now = now or datetime.now(timezone.utc)
    params = urlencode({"interval": "1d", "period1": 0, "period2": int(now.timestamp()), "events": "history"})
    request = Request(YAHOO_URL + quote(symbol, safe="") + "?" + params,
                      headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    for attempt in range(4):
        try:
            with opener(request, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8"))
            break
        except Exception:
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))
    result = (data.get("chart") or {}).get("result") or []
    if not result:
        raise RuntimeError(f"Yahoo returned no data for {symbol}: {(data.get('chart') or {}).get('error')}")
    r = result[0]
    zone = ZoneInfo(r["meta"].get("exchangeTimezoneName") or "America/New_York")
    today = now.astimezone(zone).date()
    q = r["indicators"]["quote"][0]
    bars = {}
    for k, t in enumerate(r.get("timestamp") or []):
        close = q["close"][k]
        if close is None:
            continue
        day = datetime.fromtimestamp(t, timezone.utc).astimezone(zone).date()
        if day >= today:  # the current trading day may still be forming
            continue
        bars[day] = {"day": day, "open": q["open"][k], "high": q["high"][k], "low": q["low"][k],
                     "close": float(close), "volume": q["volume"][k]}
    return [bars[d] for d in sorted(bars)]


def update_other_markets(store: OtherMarketsStore | None = None, log=print, fetch=fetch_yahoo) -> None:
    store = store or OtherMarketsStore()
    for name, (symbol, description) in MARKETS.items():
        try:
            bars = fetch(symbol)
            added, revised = store.save(name, bars)
            latest = store.latest_day(name)
            log(f"{description:<34} {added:>6,} new days, latest {latest}" +
                (f", {revised} revised value(s) noted (not applied)" if revised else ""))
        except Exception as exc:
            log(f"{description:<34} update FAILED: {exc}")
        time.sleep(1)
