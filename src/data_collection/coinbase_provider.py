import json
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.data_collection.market_data import MarketData
from src.data_collection.market_data_provider import MarketDataProvider


class CoinbaseProvider(MarketDataProvider):
    """Retrieves public historical OHLC candles from Coinbase Exchange."""

    exchange = "coinbase"
    BASE_URL = "https://api.exchange.coinbase.com/products"

    TIMEFRAMES = {
        "1m": 60,
        "5m": 300,
        "15m": 900,
        "1h": 3600,
        "6h": 21600,
        "1d": 86400,
    }

    PAIRS = {
        "BTC/USD": "BTC-USD",
        "ETH/USD": "ETH-USD",
    }

    PAGE_SIZE = 300
    REQUEST_DELAY_SECONDS = 0.15

    def fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[MarketData]:

        if symbol not in self.PAIRS:
            raise ValueError(f"Unsupported Coinbase symbol: {symbol}")

        if timeframe not in self.TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        if (
            start.tzinfo is None
            or start.utcoffset() is None
            or end.tzinfo is None
            or end.utcoffset() is None
        ):
            raise ValueError("Start and end must be timezone-aware.")

        start = start.astimezone(timezone.utc)
        end = end.astimezone(timezone.utc)

        if start >= end:
            raise ValueError("Start time must be earlier than end time.")

        granularity = self.TIMEFRAMES[timeframe]
        window_seconds = granularity * self.PAGE_SIZE
        window_start = start
        candles_by_timestamp = {}

        while window_start < end:
            window_end = min(
                window_start + timedelta(seconds=window_seconds),
                end,
            )

            params = {
                "start": window_start.isoformat(
                    timespec="seconds"
                ).replace("+00:00", "Z"),
                "end": window_end.isoformat(
                    timespec="seconds"
                ).replace("+00:00", "Z"),
                "granularity": granularity,
            }

            url = (
                f"{self.BASE_URL}/{self.PAIRS[symbol]}/candles"
                f"?{urlencode(params)}"
            )

            request = Request(
                url,
                headers={"User-Agent": "AI-Trading-System/1.0"},
            )

            try:
                with urlopen(request, timeout=30) as response:
                    data = json.loads(response.read().decode("utf-8"))
            except Exception as exc:
                raise RuntimeError(
                    f"Could not retrieve market data from Coinbase: {exc}"
                ) from exc

            if not isinstance(data, list):
                raise RuntimeError(
                    "Unexpected Coinbase candles response."
                )

            for row in data:
                if not isinstance(row, list) or len(row) != 6:
                    raise RuntimeError(
                        "Unexpected candle format in Coinbase response."
                    )

                try:
                    # Coinbase row format:
                    # [timestamp, low, high, open, close, volume]
                    timestamp = datetime.fromtimestamp(
                        int(row[0]),
                        tz=timezone.utc,
                    )

                    if start <= timestamp < end:
                        candles_by_timestamp[int(row[0])] = MarketData(
                            exchange=self.exchange,
                            symbol=symbol,
                            market="crypto",
                            timestamp=timestamp,
                            low=float(row[1]),
                            high=float(row[2]),
                            open=float(row[3]),
                            close=float(row[4]),
                            volume=float(row[5]),
                        )

                except (TypeError, ValueError, OverflowError) as exc:
                    raise RuntimeError(
                        f"Could not parse a Coinbase candle: {exc}"
                    ) from exc

            window_start = window_end
            time.sleep(self.REQUEST_DELAY_SECONDS)

        return [
            candles_by_timestamp[timestamp]
            for timestamp in sorted(candles_by_timestamp)
        ]