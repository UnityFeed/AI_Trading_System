"""
The list of strategies the system knows.

Every strategy we find or build is added here. Being on this list is what
makes it available everywhere: the Strategy tester page (full-history
backtest, per-year results, every trade), the trade markers on the chart,
and (for the one marked ACTIVE) the paper trader.

A strategy is a combination of the building blocks in
src/backtesting/conditions.py (trend filter, buy trigger, volume filter,
sell rule, optional ATR stop) on one timeframe.
"""

from dataclasses import dataclass

from src.backtesting.search import StrategySpec


@dataclass(frozen=True)
class StrategyDefinition:
    id: str  # short, stable, used in URLs
    name: str
    timeframe: str
    spec: StrategySpec
    description: str  # plain language: what it does
    origin: str  # where it came from and how it was chosen


STRATEGIES: tuple[StrategyDefinition, ...] = (
    StrategyDefinition(
        id="trend-macd-1d",
        name="Daily trend + MACD",
        timeframe="1d",
        spec=StrategySpec("ema50>ema200", "macd_cross_up", "none", "ema20_cross_down_ema50", 2.0),
        description=(
            "Buy when the long trend is up (EMA 50 above EMA 200) and MACD crosses above "
            "its signal line. Sell when EMA 20 crosses below EMA 50, or when the price "
            "closes 2x ATR below the buy price."
        ),
        origin=(
            "Step 5a candidate 1: top 10 on 2013-2021 at both fees; chosen by the "
            "walk-forward for 2022-2026 five years in a row."
        ),
    ),
    StrategyDefinition(
        id="trend-ema-cross-1d",
        name="Daily EMA 200 + EMA 20/50 cross",
        timeframe="1d",
        spec=StrategySpec("close>ema200", "ema20_cross_up_ema50", "none", "ema20_cross_down_ema50", 2.0),
        description=(
            "Buy when the price is above EMA 200 and EMA 20 crosses above EMA 50. Sell when "
            "EMA 20 crosses back below EMA 50, or on a 2x ATR stop."
        ),
        origin="Step 5a candidate 2 (top 10 on 2013-2021 at both fees).",
    ),
    StrategyDefinition(
        id="trend-dip-1d",
        name="Daily uptrend dip (RSI < 40)",
        timeframe="1d",
        spec=StrategySpec("ema50>ema200", "rsi<40", "none", "ema20_cross_down_ema50", None),
        description=(
            "Buy a dip (RSI below 40) only while the long trend is up (EMA 50 above EMA 200). "
            "Sell when EMA 20 crosses below EMA 50."
        ),
        origin="Step 5a candidate 3: the only dip-buying rule in the top 10.",
    ),
)

ACTIVE_STRATEGY_ID = "trend-macd-1d"  # followed by the paper trader


def get_strategy(strategy_id: str) -> StrategyDefinition:
    for strategy in STRATEGIES:
        if strategy.id == strategy_id:
            return strategy
    raise KeyError(f"Unknown strategy: {strategy_id}")


def active_strategy() -> StrategyDefinition:
    return get_strategy(ACTIVE_STRATEGY_ID)
