"""
Bybit spot candles (the owner's exchange, Bybit EU).

Official docs (read 24 Nov 2026):
  https://bybit-exchange.github.io/docs/v5/market/kline
  GET /v5/market/kline?category=spot&symbol=BTCUSDT&interval=60&start=&end=&limit=
  - start / end in milliseconds, limit 1..1000 (default 200)
  - list sorted NEWEST FIRST; each row [startTime, open, high, low, close,
    volume (base coin), turnover (quote coin)]
  - the newest candle may still be forming ("close is the last traded price
    when the candle is not closed"): only candles that have ended are kept
  https://bybit-exchange.github.io/docs/v5/guide
  - mainnet https://api.bybit.com; "EEA users: use https://api.bybit.eu"
Public market data needs no API key. The EU address is tried first, then the
global one. Bybit blocks some countries (HTTP 403 from CloudFront).

Pair: BTCUSDT (Bybit's main BTC spot market; USDT normally trades within
~0.1% of USD). Stored as exchange "bybit", symbol "BTC/USDT", never mixed
with the other exchanges in the database.
"""

import json
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.data_collection.market_data import MarketData
from src.data_collection.market_data_provider import MarketDataProvider


class BybitProvider(MarketDataProvider):

    exchange = "bybit"
    BASE_URLS = ("https://api.bybit.eu", "https://api.bybit.com")
    PATH = "/v5/market/kline"
    # Bybit spot opened in 2021; earlier requests simply return no candles.
    FIRST_AVAILABLE = datetime(2021, 6, 1, tzinfo=timezone.utc)

    TIMEFRAMES = {"1h": ("60", timedelta(hours=1)), "4h": ("240", timedelta(hours=4)), "1d": ("D", timedelta(days=1))}
    PAIRS = {"BTC/USDT": "BTCUSDT"}
    PAGE_SIZE = 1000
    REQUEST_DELAY_SECONDS = 0.2

    def __init__(self, base_urls: tuple[str, ...] | None = None):
        self.base_urls = base_urls or self.BASE_URLS
        self.working_url: str | None = None

    def _get(self, params: dict) -> dict:
        errors = []
        urls = [self.working_url] if self.working_url else list(self.base_urls)
        for base in urls:
            request = Request(f"{base}{self.PATH}?{urlencode(params)}",
                              headers={"User-Agent": "AI-Trading-System/1.0"})
            try:
                with urlopen(request, timeout=30) as response:
                    data = json.loads(response.read().decode("utf-8"))
            except Exception as exc:  # try the next address
                errors.append(f"{base}: {exc}")
                continue
            if data.get("retCode") != 0:
                raise RuntimeError(f"Bybit error {data.get('retCode')}: {data.get('retMsg')}")
            self.working_url = base
            return data
        raise RuntimeError("Could not retrieve market data from Bybit (" + "; ".join(errors) + ")")

    def fetch_candles(self, symbol: str, timeframe: str, start: datetime, end: datetime,
                      now: datetime | None = None) -> list[MarketData]:
        if symbol not in self.PAIRS:
            raise ValueError(f"Unsupported Bybit symbol: {symbol}")
        if timeframe not in self.TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("Start and end must be timezone-aware.")
        start, end = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
        if start >= end:
            raise ValueError("Start time must be earlier than end time.")
        interval, duration = self.TIMEFRAMES[timeframe]
        now = now or datetime.now(timezone.utc)
        found: dict[datetime, MarketData] = {}
        window_start = max(start, self.FIRST_AVAILABLE)
        while window_start < end:
            window_end = min(end, window_start + duration * self.PAGE_SIZE)
            data = self._get({
                "category": "spot", "symbol": self.PAIRS[symbol], "interval": interval,
                "start": int(window_start.timestamp() * 1000),
                "end": int((window_end - timedelta(milliseconds=1)).timestamp() * 1000),
                "limit": self.PAGE_SIZE,
            })
            for row in data.get("result", {}).get("list", []):
                try:
                    opened = datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc)
                    candle = MarketData(exchange=self.exchange, symbol=symbol, market="crypto", timestamp=opened,
                                        open=float(row[1]), high=float(row[2]), low=float(row[3]),
                                        close=float(row[4]), volume=float(row[5]))
                except (TypeError, ValueError, IndexError, OverflowError) as exc:
                    raise RuntimeError(f"Could not parse a Bybit candle: {exc}") from exc
                if start <= opened < end and opened + duration <= now:  # completed candles only
                    found[opened] = candle
            window_start = window_end
            time.sleep(self.REQUEST_DELAY_SECONDS)
        return [found[t] for t in sorted(found)]
