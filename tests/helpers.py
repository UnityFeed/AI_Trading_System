from datetime import datetime, timedelta, timezone

from src.data_collection.market_data import MarketData


BASE_TIME = datetime(2026, 11, 14, 0, 0, tzinfo=timezone.utc)


def hourly_candles(
    closes: list[float],
    start: datetime = BASE_TIME,
    exchange: str = "kraken",
    symbol: str = "BTC/USD",
    skip_hours: set[int] | None = None,
) -> list[MarketData]:
    """
    Build consecutive hourly candles from a list of closes.

    Hour offsets in skip_hours are left out, which creates a gap in the
    series (the way a missing or excluded hour looks in real data).
    """

    skip_hours = skip_hours or set()
    candles = []

    for offset, close in enumerate(closes):
        if offset in skip_hours:
            continue

        candles.append(
            MarketData(
                symbol=symbol,
                market="crypto",
                timestamp=start + timedelta(hours=offset),
                open=close,
                high=close,
                low=close,
                close=close,
                volume=1.0,
                exchange=exchange,
            )
        )

    return candles
