
import math
from datetime import datetime
from numbers import Real

from src.data_collection.market_data import MarketData


def validate_market_data(candle: MarketData) -> list[str]:
    """
    Validate a market-data candle.

    Returns an empty list if valid.
    Otherwise, returns a list of validation errors.
    """

    if not isinstance(candle, MarketData):
        return ["Input must be a MarketData object."]

    errors = []

    if not isinstance(candle.symbol, str) or not candle.symbol.strip():
        errors.append("Symbol must be a non-empty string.")

    if (
        not isinstance(candle.market, str)
        or candle.market not in {"stock", "crypto", "forex"}
    ):
        errors.append("Market must be stock, crypto, or forex.")

    if (
    not isinstance(candle.timestamp, datetime)
    or candle.timestamp.tzinfo is None
    or candle.timestamp.utcoffset() is None):
        errors.append("Timestamp must be a timezone-aware datetime value.")

    prices = {
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
    }

    valid_prices = {}

    for name, value in prices.items():
        if isinstance(value, bool) or not isinstance(value, Real):
            errors.append(f"{name} must be a number.")
        elif not math.isfinite(value):
            errors.append(f"{name} must be finite.")
        elif value <= 0:
            errors.append(f"{name} must be greater than zero.")
        else:
            valid_prices[name] = value

    if len(valid_prices) == 4:
        if valid_prices["high"] < max(
            valid_prices["open"],
            valid_prices["close"],
            valid_prices["low"],
        ):
            errors.append("High cannot be lower than another candle price.")

        if valid_prices["low"] > min(
            valid_prices["open"],
            valid_prices["close"],
            valid_prices["high"],
        ):
            errors.append("Low cannot be higher than another candle price.")

    volume = candle.volume

    if (
        isinstance(volume, bool)
        or not isinstance(volume, Real)
        or not math.isfinite(volume)
        or volume < 0
    ):
        errors.append("Volume must be a finite, non-negative number.")

    return errors
