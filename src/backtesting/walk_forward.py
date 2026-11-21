"""
Full-history checks on top of the strategy search.

1. Every combination is run ONCE over the whole history (2013 to now),
   continuously, so positions carry over year ends as they would in
   reality. Each run is summarised per calendar year (start and end value,
   worst drop, trades) right away, to keep memory small.

2. Walk-forward test: for each test year Y, pick the best combination
   using ONLY the years before Y, then record how that pick did in year Y.
   Chaining those test years gives one out-of-sample result over most of
   the history, in which no pick ever used the year it is judged on.

   Simplification: when the pick changes at a year end, the new strategy's
   continuous run is used for the new year, as if it had been followed
   all along. Switching costs at year ends are ignored (at most one extra
   buy and sell per year).
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from src.backtesting.engine import HOURS_PER_YEAR, BacktestResult
from src.backtesting.search import StrategySpec


def year_start(year: int) -> datetime:
    return datetime(year, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class PeriodStats:
    start: datetime
    end: datetime
    return_pct: float
    max_drawdown_pct: float
    trades: int

    @property
    def years(self) -> float:
        return (self.end - self.start).total_seconds() / 3600 / HOURS_PER_YEAR

    @property
    def cagr_pct(self) -> float:
        growth = 1 + self.return_pct / 100
        if self.years <= 0 or growth <= 0:
            return -100.0
        return (growth ** (1 / self.years) - 1) * 100

    @property
    def calmar(self) -> float:
        if self.max_drawdown_pct <= 0:
            return 0.0
        return self.cagr_pct / self.max_drawdown_pct


@dataclass(frozen=True)
class RunSummary:
    """Per-year figures of one continuous run."""

    years: dict[int, PeriodStats]  # result within each calendar year
    to_year_end: dict[int, PeriodStats]  # from the start of the run to each year end

    def before(self, year: int) -> PeriodStats | None:
        """Everything before 1 January of `year`."""
        return self.to_year_end.get(year - 1)


def curve_stats(
    curve: list[tuple[datetime, float]],
    start: datetime,
    end: datetime,
    trades: int,
) -> PeriodStats | None:
    """Stats for the curve points in [start, end), starting from the last value before start."""

    base = 1.0
    peak = None
    max_drawdown = 0.0
    first = last = None
    last_value = None

    for timestamp, value in curve:
        if timestamp < start:
            base = value
            continue
        if timestamp >= end:
            break
        if peak is None:
            peak = base
            first = timestamp
        peak = max(peak, value)
        max_drawdown = max(max_drawdown, (peak - value) / peak)
        last, last_value = timestamp, value

    if first is None:
        return None

    return PeriodStats(first, last, (last_value / base - 1) * 100, max_drawdown * 100, trades)


def summarize(result: BacktestResult) -> RunSummary:
    """Per-year summary of a run made with record_equity=True (one pass)."""

    curve = result.equity_curve
    if not curve:
        raise ValueError("The result has no equity curve (use record_equity=True).")

    entry_years = [t.entry_time.year for t in result.trades]
    run_start = curve[0][0]

    years = {}
    to_year_end = {}

    overall_peak = 1.0
    overall_drawdown = 0.0
    year = None
    year_base = 1.0
    year_peak = year_drawdown = 0.0
    year_first = previous_time = None
    previous_value = 1.0

    def close_year():
        years[year] = PeriodStats(
            year_first, previous_time,
            (previous_value / year_base - 1) * 100, year_drawdown * 100,
            sum(y == year for y in entry_years),
        )
        to_year_end[year] = PeriodStats(
            run_start, previous_time,
            (previous_value - 1) * 100, overall_drawdown * 100,
            sum(y <= year for y in entry_years),
        )

    for timestamp, value in curve:
        if timestamp.year != year:
            if year is not None:
                close_year()
            year = timestamp.year
            year_base = previous_value
            year_peak = year_base
            year_drawdown = 0.0
            year_first = timestamp

        overall_peak = max(overall_peak, value)
        overall_drawdown = max(overall_drawdown, (overall_peak - value) / overall_peak)
        year_peak = max(year_peak, value)
        year_drawdown = max(year_drawdown, (year_peak - value) / year_peak)
        previous_time, previous_value = timestamp, value

    close_year()
    return RunSummary(years, to_year_end)


@dataclass(frozen=True)
class WalkForwardYear:
    year: int
    spec: StrategySpec
    training_calmar: float
    strategy: PeriodStats
    buy_and_hold: PeriodStats


def walk_forward(
    summaries: dict[StrategySpec, RunSummary],
    benchmark: RunSummary,
    test_years: list[int],
    min_trades_per_year: float,
) -> list[WalkForwardYear]:
    """
    For each test year, choose the combination with the best calmar over
    everything before that year (with enough trades), and report its
    result in that year next to buy-and-hold.
    """

    picks = []

    for year in test_years:
        best = None

        for spec, summary in summaries.items():
            training = summary.before(year)
            if training is None or training.trades < min_trades_per_year * training.years:
                continue
            if best is None or training.calmar > best[0]:
                best = (training.calmar, spec)

        if best is None:
            continue

        tested = summaries[best[1]].years.get(year)
        held = benchmark.years.get(year)
        if tested is None or held is None:
            continue

        picks.append(WalkForwardYear(year, best[1], best[0], tested, held))

    return picks


def stitched_curve(
    picks: list[WalkForwardYear],
    full_runs: dict[StrategySpec, BacktestResult],
) -> list[tuple[datetime, float]]:
    """
    One account-value curve that follows each year's pick in that year.
    `full_runs` must hold record_equity runs of every picked spec.
    """

    stitched = []
    level = 1.0

    for pick in picks:
        curve = full_runs[pick.spec].equity_curve
        start, end = year_start(pick.year), year_start(pick.year + 1)
        base = None
        last = None

        for timestamp, value in curve:
            if timestamp < start:
                base = value
                continue
            if timestamp >= end:
                break
            if base is None:
                base = 1.0
            stitched.append((timestamp, level * value / base))
            last = value

        if last is not None:
            level *= last / base

    return stitched


def chain_returns(stats: list[PeriodStats]) -> float:
    """Total return in % of following the periods one after another."""
    growth = 1.0
    for item in stats:
        growth *= 1 + item.return_pct / 100
    return (growth - 1) * 100
