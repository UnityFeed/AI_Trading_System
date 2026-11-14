
from datetime import datetime, timezone

from src.data_collection.market_data import MarketData


class HourlyTradeAggregator:
    """
    Converts individual Kraken trades into hourly OHLCV candles.
    """

    EXCHANGE = "kraken"
    SYMBOL = "BTC/USD"
    MARKET = "crypto"

    def aggregate(
        self,
        trades: list[tuple[datetime, float, float]],
    ) -> list[MarketData]:

        if not trades:
            return []

        # Sort trades chronologically to preserve correct open and close.
        trades = sorted(trades, key=lambda trade: trade[0])

        hourly = {}

        for timestamp, price, volume in trades:

            if (
                timestamp.tzinfo is None
                or timestamp.utcoffset() is None
            ):
                raise ValueError(
                    "Trade timestamps must be timezone-aware."
                )

            timestamp = timestamp.astimezone(timezone.utc)

            hour = timestamp.replace(
                minute=0,
                second=0,
                microsecond=0,
            )

            if hour not in hourly:
                hourly[hour] = {
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "volume": volume,
                }

            else:
                candle = hourly[hour]

                candle["high"] = max(candle["high"], price)
                candle["low"] = min(candle["low"], price)
                candle["close"] = price
                candle["volume"] += volume

        candles = []

        for timestamp, values in sorted(hourly.items()):

            candles.append(
                MarketData(
                    exchange=self.EXCHANGE,
                    symbol=self.SYMBOL,
                    market=self.MARKET,
                    timestamp=timestamp,
                    open=values["open"],
                    high=values["high"],
                    low=values["low"],
                    close=values["close"],
                    volume=values["volume"],
                )
            )

        return candles
