
import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.data_collection.market_data import MarketData
from src.data_collection.market_data_provider import MarketDataProvider


class KrakenProvider(MarketDataProvider):
   
    """
    Retrieves public OHLC market data from Kraken.
    No API key is required.
    """
    exchange = "kraken"
    
    BASE_URL = "https://api.kraken.com/0/public/OHLC"

    TIMEFRAMES = {
        "1m": 1,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "1h": 60,
        "4h": 240,
        "1d": 1440,
        "1w": 10080,
    }

    PAIRS = {
        "BTC/USD": "XBTUSD",
        "ETH/USD": "ETHUSD",
    }

    def fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[MarketData]:

        if symbol not in self.PAIRS:
            raise ValueError(f"Unsupported Kraken symbol: {symbol}")

        if timeframe not in self.TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        if (
            start.tzinfo is None
            or start.utcoffset() is None
            or end.tzinfo is None
            or end.utcoffset() is None
        ):
            raise ValueError("Start and end must be timezone-aware.")

        if start >= end:
            raise ValueError("Start time must be earlier than end time.")

        params = {
            "pair": self.PAIRS[symbol],
            "interval": self.TIMEFRAMES[timeframe],
            "since": int(start.timestamp()),
        }

        request = Request(
            f"{self.BASE_URL}?{urlencode(params)}",
            headers={"User-Agent": "AI-Trading-System/1.0"},
        )

        try:
            with urlopen(request, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))

        except Exception as exc:
            raise RuntimeError(
                f"Could not retrieve market data from Kraken: {exc}"
            ) from exc

        if data.get("error"):
            raise RuntimeError(
                f"Kraken API error: {data['error']}"
            )

        result = data.get("result", {})

        pair_keys = [key for key in result if key != "last"]

        if len(pair_keys) != 1:
            raise RuntimeError("Unexpected Kraken OHLC response.")

        raw_candles = result[pair_keys[0]]

        # Kraken's final candle is still being formed.
        # Exclude it from our historical data.
        completed_candles = raw_candles[:-1]

        candles = []

        for row in completed_candles:

            timestamp = datetime.fromtimestamp(
                int(row[0]),
                tz=timezone.utc,
            )

            if not start <= timestamp < end:
                continue

            candles.append(
                MarketData(
                    exchange="kraken",
                    symbol=symbol,
                    market="crypto",
                    timestamp=timestamp,
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[6]),
                )
            )

        return candles
