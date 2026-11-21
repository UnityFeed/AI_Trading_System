"""
Building blocks for long-only (buy low, sell high) strategies.

Each condition is calculated once for the whole market and returns one
True/False per candle. A condition at candle i only looks at the
indicator values of candle i and, for crossings, candle i-1, so it is
known at the close of candle i. Values that are not warmed up yet make a
condition False. A crossing is only counted between two consecutive
candles, never across a gap.

Entry conditions are grouped in three roles, and a strategy picks one of
each (the "none" option switches a role off):
- trend filter: is the bigger trend up? (only buy dips in an uptrend)
- trigger: is this a good moment to buy? (oversold, momentum turning)
- volume filter: is there unusual interest?

Exit conditions say when to sell. A strategy may also use an ATR stop,
which the engine handles (it needs the entry price).
"""

from collections.abc import Callable

from src.backtesting.market import Market


def _value(market: Market, i: int, name: str):
    return market.rows[i].values.get(name)


def _compare(market: Market, a: str, b: str | float, above: bool) -> list[bool]:
    """a > b (above) or a < b, where a/b are value names ("close" = the candle
    close) and b may also be a fixed number. Missing values give False."""

    def pick(row, name):
        return row.close if name == "close" else row.values.get(name)

    result = []
    for row in market.rows:
        left = pick(row, a)
        right = b if isinstance(b, (int, float)) else pick(row, b)
        if left is None or right is None:
            result.append(False)
        else:
            result.append(left > right if above else left < right)
    return result


def _above(market: Market, a: str, b: str | float) -> list[bool]:
    return _compare(market, a, b, above=True)


def _below(market: Market, a: str, b: str | float) -> list[bool]:
    return _compare(market, a, b, above=False)


def _cross(market: Market, fast: str, slow: str, upward: bool) -> list[bool]:
    """fast crosses slow between candle i-1 and candle i."""

    result = [False] * len(market.rows)

    for i in range(1, len(market.rows)):
        if not market.consecutive[i]:
            continue

        f0, s0 = _value(market, i - 1, fast), _value(market, i - 1, slow)
        f1, s1 = _value(market, i, fast), _value(market, i, slow)

        if None in (f0, s0, f1, s1):
            continue

        if upward:
            result[i] = f0 <= s0 and f1 > s1
        else:
            result[i] = f0 >= s0 and f1 < s1

    return result


def _always(market: Market) -> list[bool]:
    return [True] * len(market.rows)


Condition = Callable[[Market], list[bool]]

TREND_FILTERS: dict[str, Condition] = {
    "none": _always,
    "close>ema200": lambda m: _above(m, "close", "ema_200"),
    "ema50>ema200": lambda m: _above(m, "ema_50", "ema_200"),
}

TRIGGERS: dict[str, Condition] = {
    "rsi<30": lambda m: _below(m, "rsi_14", 30),
    "rsi<40": lambda m: _below(m, "rsi_14", 40),
    "close<bb_lower": lambda m: _below(m, "close", "bb_lower"),
    "macd_cross_up": lambda m: _cross(m, "macd", "macd_signal", upward=True),
    "ema20_cross_up_ema50": lambda m: _cross(m, "ema_20", "ema_50", upward=True),
}

VOLUME_FILTERS: dict[str, Condition] = {
    "none": _always,
    "relvol>1.5": lambda m: _above(m, "relative_volume_20", 1.5),
}

EXITS: dict[str, Condition] = {
    "rsi>70": lambda m: _above(m, "rsi_14", 70),
    "rsi>50": lambda m: _above(m, "rsi_14", 50),
    "close>bb_middle": lambda m: _above(m, "close", "bb_middle"),
    "close>bb_upper": lambda m: _above(m, "close", "bb_upper"),
    "macd_cross_down": lambda m: _cross(m, "macd", "macd_signal", upward=False),
    "ema20_cross_down_ema50": lambda m: _cross(m, "ema_20", "ema_50", upward=False),
}

# ATR stop multiples; None means no stop.
STOPS: tuple[float | None, ...] = (None, 2.0, 3.0)


def strategy_signals(blocks: dict, spec) -> tuple[list[bool], list[bool]]:
    """
    Buy and sell signals of one strategy (a StrategySpec) from the
    building blocks returned by evaluate_all: buy when the trend filter,
    the trigger and the volume filter are all true.
    """
    entry = [
        trend and trigger and volume
        for trend, trigger, volume in zip(
            blocks["trend"][spec.trend],
            blocks["trigger"][spec.trigger],
            blocks["volume"][spec.volume],
        )
    ]
    return entry, blocks["exit"][spec.exit]


def evaluate_all(market: Market) -> dict[str, dict[str, list[bool]]]:
    """Calculate every building block once."""

    return {
        "trend": {name: fn(market) for name, fn in TREND_FILTERS.items()},
        "trigger": {name: fn(market) for name, fn in TRIGGERS.items()},
        "volume": {name: fn(market) for name, fn in VOLUME_FILTERS.items()},
        "exit": {name: fn(market) for name, fn in EXITS.items()},
    }
