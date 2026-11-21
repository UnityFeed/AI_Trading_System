"""
Search for long-only strategies that hold up on real data.

The danger with trying hundreds of indicator combinations is that some
will look great by pure luck ("overfitting"): they fit the past, not a
real pattern. To guard against that, history is split into three windows:

  1. bitstamp era   2013-10 .. 2016-12   (selection)
  2. kraken era     2017-01 .. 2021-12   (selection)
  3. unseen         2022-01 .. now       (test only)

A combination is only selected when it worked in BOTH selection windows
(two very different markets), judged by its weakest window. Window 3 is
never used to choose anything; it shows how the chosen combinations do on
years they were not picked on. Only results that also hold in window 3
point at a real "common ground".

Each window starts with cash and no position. Indicators are calculated
on the full history beforehand; they only ever use past candles, so this
does not leak future information into a window.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import product

from src.backtesting.conditions import (
    EXITS,
    STOPS,
    TREND_FILTERS,
    TRIGGERS,
    VOLUME_FILTERS,
    evaluate_all,
    strategy_signals,
)
from src.backtesting.engine import (
    BacktestResult,
    CostSettings,
    buy_and_hold,
    run_backtest,
)
from src.backtesting.market import Market


WINDOWS = (
    ("bitstamp era", datetime(2013, 1, 1, tzinfo=timezone.utc),
     datetime(2017, 1, 1, tzinfo=timezone.utc)),
    ("kraken era", datetime(2017, 1, 1, tzinfo=timezone.utc),
     datetime(2022, 1, 1, tzinfo=timezone.utc)),
    ("unseen", datetime(2022, 1, 1, tzinfo=timezone.utc),
     datetime(2100, 1, 1, tzinfo=timezone.utc)),
)
SELECTION_WINDOWS = ("bitstamp era", "kraken era")
TEST_WINDOW = "unseen"


@dataclass(frozen=True)
class StrategySpec:
    trend: str
    trigger: str
    volume: str
    exit: str
    stop_atr: float | None

    @property
    def name(self) -> str:
        parts = [] if self.trend == "none" else [self.trend]
        parts.append(self.trigger)
        if self.volume != "none":
            parts.append(self.volume)
        stop = f", stop {self.stop_atr:g}xATR" if self.stop_atr else ""
        return f"BUY {' & '.join(parts)} | SELL {self.exit}{stop}"


@dataclass(frozen=True)
class StrategyScore:
    spec: StrategySpec
    results: dict[str, BacktestResult]  # window name -> result

    def selection_score(self, min_trades: int) -> float | None:
        """Weakest Calmar over the selection windows; None if too few trades."""
        selected = [self.results[w] for w in SELECTION_WINDOWS]
        if any(len(r.trades) < min_trades for r in selected):
            return None
        return min(r.calmar for r in selected)


def all_specs() -> list[StrategySpec]:
    return [
        StrategySpec(trend, trigger, volume, exit_name, stop)
        for trend, trigger, volume, exit_name, stop in product(
            TREND_FILTERS, TRIGGERS, VOLUME_FILTERS, EXITS, STOPS
        )
    ]


def window_ranges(market: Market) -> dict[str, range]:
    ranges = {}
    for name, start, end in WINDOWS:
        window = market.index_range(start, end)
        if len(window) > 0:
            ranges[name] = window
    return ranges


def benchmark(market: Market, costs: CostSettings) -> dict[str, BacktestResult]:
    return {
        name: buy_and_hold(market, window, costs)
        for name, window in window_ranges(market).items()
    }


def search(
    market: Market,
    costs: CostSettings = CostSettings(),
    specs: list[StrategySpec] | None = None,
) -> list[StrategyScore]:
    """Backtest every strategy spec in every window."""

    blocks = evaluate_all(market)
    windows = window_ranges(market)
    scores = []

    for spec in specs if specs is not None else all_specs():
        entry, exit_signal = strategy_signals(blocks, spec)

        results = {
            name: run_backtest(
                market, window, entry, exit_signal, spec.stop_atr, costs
            )
            for name, window in windows.items()
        }
        scores.append(StrategyScore(spec, results))

    return scores


def rank_by_selection(
    scores: list[StrategyScore], min_trades: int
) -> list[tuple[float, StrategyScore]]:
    ranked = [
        (score.selection_score(min_trades), score)
        for score in scores
    ]
    ranked = [(value, score) for value, score in ranked if value is not None]
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked
