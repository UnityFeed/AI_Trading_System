"""
Training coins (owner, 24 Nov 2026: "train the AI on other coins... pure
training, I don't need to track or trade them"): hourly candles of the five
largest coins after BTC, used ONLY as extra examples for the AI's pattern
experts. Never shown, traded or used for BTC's own indicators.

Coins: the top 5 by market value after BTC, without stablecoins (CoinGecko,
24 Nov 2026): ETH, BNB, XRP, SOL, TRX.

Source: Binance's public market-data address (no key), documented in
github.com/binance/binance-spot-api-docs rest-api.md (read 24 Nov 2026):
  https://data-api.binance.vision/api/v3/klines?symbol=ETHUSDT&interval=1h
  &startTime=&endTime=&limit=1000   (ms, max 1000, oldest first; rows
  [open time, open, high, low, close, volume, close time, ...])
Binance has the longest hourly USDT histories for these coins (ETH from Aug
2017). The newest candle may still be forming: only ended candles are kept.

Stored in its own SQLite file (database/training_coins.db, same table layout
as the market database, exchange "binance", symbols like "ETH/USDT"), never
in the market database. Gaps (exchange maintenance) stay gaps.
"""

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.analysis.primary_history import PRIMARY_LABEL, ContinuousHistory
from src.data_collection.market_data import MarketData
from src.data_collection.market_data_repository import MarketDataRepository


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = PROJECT_ROOT / "database" / "training_coins.db"
URL = "https://data-api.binance.vision/api/v3/klines"
COINS = {"ETH": "ETHUSDT", "BNB": "BNBUSDT", "XRP": "XRPUSDT", "SOL": "SOLUSDT", "TRX": "TRXUSDT"}
EXCHANGE = "binance"
FIRST = datetime(2017, 7, 1, tzinfo=timezone.utc)  # Binance opened in July 2017
HOUR = timedelta(hours=1)
PAGE = 1000


def symbol_of(coin: str) -> str:
    return f"{coin}/USDT"


def fetch_klines(coin: str, start: datetime, end: datetime, now: datetime | None = None,
                 opener=urlopen, delay: float = 0.1) -> list[MarketData]:
    """Completed hourly candles of `coin` in [start, end), oldest first."""
    now = now or datetime.now(timezone.utc)
    out: dict[datetime, MarketData] = {}
    window = start
    while window < end:
        params = {"symbol": COINS[coin], "interval": "1h", "startTime": int(window.timestamp() * 1000),
                  "endTime": int(min(end, window + PAGE * HOUR).timestamp() * 1000) - 1, "limit": PAGE}
        request = Request(f"{URL}?{urlencode(params)}", headers={"User-Agent": "AI-Trading-System/1.0"})
        for attempt in range(4):
            try:
                with opener(request, timeout=30) as response:
                    rows = json.loads(response.read().decode("utf-8"))
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2 * (attempt + 1))
        if not isinstance(rows, list):
            raise RuntimeError(f"Unexpected Binance response for {coin}: {str(rows)[:200]}")
        for r in rows:
            opened = datetime.fromtimestamp(int(r[0]) / 1000, tz=timezone.utc)
            if start <= opened < end and opened + HOUR <= now:
                out[opened] = MarketData(symbol_of(coin), "crypto", opened, float(r[1]), float(r[2]), float(r[3]),
                                         float(r[4]), float(r[5]), EXCHANGE)
        # no candles in this window (before the coin was listed): jump a full page
        window = window + PAGE * HOUR
        time.sleep(delay)
    return [out[t] for t in sorted(out)]


def update_training_coins(repository: MarketDataRepository | None = None, log=print, fetch=fetch_klines) -> None:
    """Forward update of every training coin (the first run downloads everything since 2017)."""
    repository = repository or MarketDataRepository(DEFAULT_PATH)
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    for coin in COINS:
        latest = repository.get_latest_candle_timestamp(symbol=symbol_of(coin), market="crypto", timeframe="1h",
                                                        exchange=EXCHANGE)
        start = FIRST if latest is None else latest.astimezone(timezone.utc) + HOUR
        if start >= end:
            log(f"{coin}: up to date")
            continue
        try:
            candles = fetch(coin, start, end)
            repository.save_candles(candles, timeframe="1h")
            log(f"{coin}: {len(candles):,} new hourly candles" + (" (first download)" if latest is None else ""))
        except Exception as exc:  # training data: a failure is reported, never fatal
            log(f"{coin}: update FAILED: {exc}")


def coin_histories(repository: MarketDataRepository | None = None) -> dict[str, ContinuousHistory]:
    """Every stored training coin as a history (same shape as BTC's, all hours from Binance)."""
    repository = repository or MarketDataRepository(DEFAULT_PATH)
    out = {}
    for coin in COINS:
        candles = repository.get_candles(symbol=symbol_of(coin), market="crypto", timeframe="1h",
                                         start=FIRST, end=datetime.now(timezone.utc) + HOUR, exchange=EXCHANGE)
        candles = [c for c in candles if c.volume > 0]  # no trades = no real price (as for BTC)
        if len(candles) < 24 * 400:
            continue
        relabelled = [MarketData(c.symbol, c.market, c.timestamp, c.open, c.high, c.low, c.close, c.volume,
                                 PRIMARY_LABEL) for c in candles]
        sources = {c.timestamp: EXCHANGE for c in candles}
        out[coin] = ContinuousHistory(relabelled, sources, dict(sources), [], [])
    return out
