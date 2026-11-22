"""
Extra measurements for any backtest result (roadmap 9a), from its daily
account values:

- Sharpe ratio: average daily return / its standard deviation, x sqrt(365)
  (return per unit of day-to-day swings; 0 risk-free rate)
- Sortino ratio: like Sharpe, but only falling days count as risk
- top-days capture: BTC's best days carry most of its gains. Of the gain
  on the 20 best BTC days, how much did the strategy get? 100% = all of it
  (fully invested on each of them), 0% = in cash on all of them.
- break-even fee: the fee per side at which the strategy would end level
  with buy-and-hold. Above it, holding wins. Below it, the strategy wins.
- turnover per year: value traded as a share of the account (a full buy
  and a full sell = 2.0)
"""

import math
from collections.abc import Callable
from datetime import datetime

from src.backtesting.engine import BacktestResult, CostSettings


DAYS_PER_YEAR = 365.0


def daily_values(curve: list[tuple[datetime, float]]) -> dict[datetime, float]:
    """Account value at the last candle of each UTC day."""
    values = {}
    for timestamp, value in curve:
        values[timestamp.replace(hour=0, minute=0, second=0, microsecond=0)] = value
    return values


def daily_returns(curve: list[tuple[datetime, float]]) -> list[tuple[datetime, float]]:
    values = sorted(daily_values(curve).items())
    out = []
    for (_, before), (day, after) in zip(values, values[1:]):
        if before > 0:
            out.append((day, after / before - 1.0))
    return out


def sharpe(returns: list[float], periods_per_year: float = DAYS_PER_YEAR) -> float:
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    if variance <= 0:
        return 0.0
    return mean / math.sqrt(variance) * math.sqrt(periods_per_year)


def sortino(returns: list[float], periods_per_year: float = DAYS_PER_YEAR) -> float:
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    downside = math.sqrt(sum(min(r, 0.0) ** 2 for r in returns) / len(returns))
    if downside <= 0:
        return 0.0
    return mean / downside * math.sqrt(periods_per_year)


def top_days_capture(result: BacktestResult, held: BacktestResult, n: int = 20) -> float | None:
    """Share (0..1) of buy-and-hold's gain on its n best days that the strategy also made."""
    strategy = dict(daily_returns(result.equity_curve))
    hold = daily_returns(held.equity_curve)
    best = sorted(hold, key=lambda item: item[1], reverse=True)[:n]
    total = sum(r for _, r in best)
    if total <= 0:
        return None
    return sum(strategy.get(day, 0.0) for day, _ in best) / total


def break_even_fee(
    run: Callable[[CostSettings], BacktestResult],
    hold: Callable[[CostSettings], BacktestResult],
    slippage_pct: float,
    highest: float = 5.0,
) -> float | None:
    """
    Fee per side (%) at which run() ends level with hold(). None: it does
    not beat holding even without fees. `highest`: it still wins at that fee.
    """
    def edge(fee: float) -> float:
        costs = CostSettings(fee_pct=fee, slippage_pct=slippage_pct)
        return run(costs).final_equity - hold(costs).final_equity

    if edge(0.0) <= 0:
        return None
    if edge(highest) > 0:
        return highest
    low, high = 0.0, highest
    for _ in range(18):
        middle = (low + high) / 2
        if edge(middle) > 0:
            low = middle
        else:
            high = middle
    return round((low + high) / 2, 3)


def risk_metrics(result: BacktestResult, held: BacktestResult) -> dict:
    """Sharpe, Sortino, top-20-days capture and turnover; both need equity curves."""
    returns = [r for _, r in daily_returns(result.equity_curve)]
    capture = top_days_capture(result, held)
    return {
        "sharpe": round(sharpe(returns), 3),
        "sortino": round(sortino(returns), 3),
        "top20_capture_pct": None if capture is None else round(capture * 100, 1),
        "turnover_per_year": round(result.turnover / result.years, 2) if result.years > 0 else None,
    }
