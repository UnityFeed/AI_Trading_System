import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.data_collection.market_data import MarketData
from src.data_collection.market_data_provider import MarketDataProvider


class BitstampProvider(MarketDataProvider):
    """Retrieves public historical OHLC candles from Bitstamp."""

    exchange = "bitstamp"
    BASE_URL = "https://www.bitstamp.net/api/v2/ohlc"

    TIMEFRAMES = {
        "1m": 60,
        "3m": 180,
        "5m": 300,
        "15m": 900,
        "30m": 1800,
        "1h": 3600,
        "2h": 7200,
        "4h": 14400,
        "6h": 21600,
        "12h": 43200,
        "1d": 86400,
        "3d": 259200,
    }

    PAIRS = {
        "BTC/USD": "btcusd",
        "ETH/USD": "ethusd",
    }

    PAGE_SIZE = 1000

    def fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[MarketData]:

        if symbol not in self.PAIRS:
            raise ValueError(f"Unsupported Bitstamp symbol: {symbol}")

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

        step = self.TIMEFRAMES[timeframe]
        start_timestamp = int(start.timestamp())
        cursor = int(end.timestamp()) - 1
        candles_by_timestamp = {}

        while cursor >= start_timestamp:
            params = {
                "step": step,
                "limit": self.PAGE_SIZE,
                "end": cursor,
                "exclude_current_candle": "true",
            }

            url = (
                f"{self.BASE_URL}/{self.PAIRS[symbol]}/"
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
                    f"Could not retrieve market data from Bitstamp: {exc}"
                ) from exc

            try:
                raw_candles = data["data"]["ohlc"]
            except (KeyError, TypeError) as exc:
                raise RuntimeError(
                    "Unexpected Bitstamp OHLC response."
                ) from exc

            if not raw_candles:
                break

            page_timestamps = []

            for row in raw_candles:
                try:
                    timestamp_seconds = int(row["timestamp"])
                    timestamp = datetime.fromtimestamp(
                        timestamp_seconds,
                        tz=timezone.utc,
                    )

                    page_timestamps.append(timestamp_seconds)

                    if start <= timestamp < end:
                        candles_by_timestamp[timestamp_seconds] = MarketData(
                            exchange=self.exchange,
                            symbol=symbol,
                            market="crypto",
                            timestamp=timestamp,
                            open=float(row["open"]),
                            high=float(row["high"]),
                            low=float(row["low"]),
                            close=float(row["close"]),
                            volume=float(row["volume"]),
                        )

                except (KeyError, TypeError, ValueError, OverflowError) as exc:
                    raise RuntimeError(
                        f"Could not parse a Bitstamp candle: {exc}"
                    ) from exc

            oldest_timestamp = min(page_timestamps)

            if oldest_timestamp <= start_timestamp:
                break

            next_cursor = oldest_timestamp - 1

            if next_cursor >= cursor:
                raise RuntimeError(
                    "Bitstamp OHLC pagination did not move backwards."
                )

            if len(raw_candles) < self.PAGE_SIZE:
                break

            cursor = next_cursor

        return [
            candles_by_timestamp[timestamp]
            for timestamp in sorted(candles_by_timestamp)
        ]