"""
List every missing Kraken hour in the primary period (from 2017-01-01) and
ask Kraken's public Trades API whether any trades happened in it.

- "trades found": Kraken has real trades for that hour, so the candle can
  be rebuilt from them (HistoricalBackfillService). Nothing is rebuilt by
  this script.
- "no trades": nothing was traded on Kraken then (usually an exchange
  outage or maintenance). The hour stays a gap.

Why it matters: a single missing hour removes the whole day (and 4h
period) from the derived candles, and every indicator restarts after it.
On daily candles the 200-day EMA then needs 200 new days to warm up.

The database is only read. One small API request per gap, with a pause
between requests to stay within Kraken's public rate limits.

Usage:
    python -m scripts.check_kraken_gaps
"""

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.analysis.primary_history import KRAKEN_PRIMARY_FROM
from src.data_collection.market_data_repository import MarketDataRepository


HOUR = timedelta(hours=1)
TRADES_URL = "https://api.kraken.com/0/public/Trades"
REQUEST_PAUSE_SECONDS = 2.0


def find_gaps(timestamps: list[datetime]) -> list[tuple[datetime, datetime]]:
    """Return (first missing hour, first hour after the gap) pairs."""

    gaps = []

    for previous, current in zip(timestamps, timestamps[1:]):
        if current - previous > HOUR:
            gaps.append((previous + HOUR, current))

    return gaps


def first_trade_between(start: datetime, end: datetime) -> datetime | None:
    """First Kraken XBTUSD trade at or after start, if it is before end."""

    since = int(start.timestamp()) * 1_000_000_000 - 1
    request = Request(
        f"{TRADES_URL}?{urlencode({'pair': 'XBTUSD', 'since': since})}",
        headers={"User-Agent": "AI-Trading-System/1.0"},
    )

    with urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))

    if data.get("error"):
        raise RuntimeError(f"Kraken API error: {data['error']}")

    pair_keys = [key for key in data["result"] if key != "last"]
    trades = data["result"][pair_keys[0]]

    for trade in trades:
        timestamp = datetime.fromtimestamp(float(trade[2]), tz=timezone.utc)

        if timestamp >= end:
            return None

        if timestamp >= start:
            return timestamp

    return None


def main(db_path: Path | None = None) -> None:

    repository = MarketDataRepository(db_path) if db_path else MarketDataRepository()

    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    timestamps = [
        timestamp.astimezone(timezone.utc)
        for timestamp in repository.get_candle_timestamps(
            symbol="BTC/USD",
            market="crypto",
            timeframe="1h",
            start=KRAKEN_PRIMARY_FROM,
            end=end,
            exchange="kraken",
        )
    ]

    print("KRAKEN GAP CHECK (primary period)")
    print("=================================")
    print(f"From {KRAKEN_PRIMARY_FROM.date()} to {end.isoformat()}")
    print(f"Stored Kraken hours: {len(timestamps):,}")

    if not timestamps:
        print("No Kraken candles stored.")
        return

    if timestamps[0] > KRAKEN_PRIMARY_FROM:
        print(f"Note: first stored hour is {timestamps[0].isoformat()}")

    gaps = find_gaps(timestamps)
    missing_hours = sum(int((b - a) / HOUR) for a, b in gaps)

    print(f"Gaps: {len(gaps)}  Missing hours: {missing_hours}")
    print()
    print(f"{'Gap start (UTC)':<26}{'Hours':>6}  Kraken trades")

    recoverable_hours = 0
    recoverable_gaps = 0

    for gap_start, gap_end in gaps:

        hours = int((gap_end - gap_start) / HOUR)

        try:
            first = first_trade_between(gap_start, gap_end)
        except Exception as exc:
            print(f"{gap_start.isoformat():<26}{hours:>6}  check failed: {exc}")
            time.sleep(REQUEST_PAUSE_SECONDS)
            continue

        if first is None:
            status = "no trades (outage?)"
        else:
            status = f"trades found, first at {first.strftime('%H:%M:%S')}"
            recoverable_hours += hours
            recoverable_gaps += 1

        print(f"{gap_start.isoformat():<26}{hours:>6}  {status}")
        time.sleep(REQUEST_PAUSE_SECONDS)

    print()
    print(
        f"Gaps with Kraken trades: {recoverable_gaps} "
        f"(up to {recoverable_hours} hours could be rebuilt from trades)"
    )
    print(
        "Note: a gap with trades may still contain individual hours without "
        "any; those stay gaps after a rebuild."
    )
    print()
    print("Check complete. The database was only read.")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
