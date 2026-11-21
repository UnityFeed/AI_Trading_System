"""
Report on the continuous history: which hours were filled from another
exchange, which hours no exchange has, and how large the price jumps are
where the series switches between exchanges.

The database is only read; the series is built in memory.

Usage:
    python -m scripts.report_continuous_history
    python -m scripts.report_continuous_history path\\to\\other.db
"""

import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.analysis.primary_history import LARGE_JUMP_PCT, get_continuous_history
from src.analysis.timeframes import aggregate_hourly_candles, split_into_runs
from src.data_collection.market_data_repository import MarketDataRepository


HISTORY_START = datetime(2013, 1, 1, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)


def hour_ranges(hours: list[datetime]) -> list[tuple[datetime, int]]:
    """Group consecutive hours: (first hour, number of hours)."""

    ranges = []

    for hour in hours:
        if ranges and ranges[-1][0] + HOUR * ranges[-1][1] == hour:
            ranges[-1] = (ranges[-1][0], ranges[-1][1] + 1)
        else:
            ranges.append((hour, 1))

    return ranges


def main(db_path: Path | None = None) -> None:

    repository = MarketDataRepository(db_path) if db_path else MarketDataRepository()
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    history = get_continuous_history(repository=repository, start=HISTORY_START, end=end)
    candles = history.candles

    print("CONTINUOUS HISTORY REPORT")
    print("=========================")

    if not candles:
        print("No candles.")
        return

    print(f"From {candles[0].timestamp.isoformat()} to {candles[-1].timestamp.isoformat()}")
    print(f"Hourly candles: {len(candles):,}")
    print()

    print("Candles by real source (primary period -> source):")
    pairs = Counter(
        (history.primary_by_hour[c.timestamp], history.sources[c.timestamp])
        for c in candles
    )
    for (primary, source), count in sorted(pairs.items()):
        label = "own data" if primary == source else "FILLED"
        print(f"  {primary:<9} period from {source:<9} {count:>8,}  {label}")
    print()

    substituted = history.substituted_hours()
    print(f"Filled hours: {len(substituted):,} in {len(hour_ranges(substituted)):,} stretches")
    for timeframe in ("4h", "1d"):
        print(
            f"  {timeframe} candles containing filled hours: "
            f"{len(history.periods_with_substitutes(timeframe)):,}"
        )
    print()

    unfilled = hour_ranges(history.unfilled_hours)
    print(f"Hours no exchange has (still gaps): {len(history.unfilled_hours):,}")
    for first, count in unfilled[:20]:
        print(f"  {first.isoformat()}  {count} h")
    if len(unfilled) > 20:
        print(f"  ... and {len(unfilled) - 20} more stretches")
    print()

    changes = history.source_changes
    jumps = sorted(abs(c.jump_pct) for c in changes)
    large = sorted(history.large_jumps(), key=lambda c: abs(c.jump_pct), reverse=True)

    print(f"Switches between exchanges: {len(changes):,}")
    if jumps:
        print(f"  median price jump: {jumps[len(jumps) // 2]:.3f}%")
        print(f"  largest price jump: {jumps[-1]:.3f}%")
    print(f"  jumps above {LARGE_JUMP_PCT}%: {len(large)}")
    for change in large[:20]:
        print(
            f"    {change.timestamp.isoformat()}  {change.from_exchange} -> "
            f"{change.to_exchange}  {change.previous_close:,.2f} -> "
            f"{change.open:,.2f}  ({change.jump_pct:+.2f}%)"
        )
    print()

    print("Unbroken runs (indicators restart only at these breaks):")
    for timeframe in ("1h", "4h", "1d"):
        series = aggregate_hourly_candles(candles, timeframe).candles
        runs = split_into_runs(series, timeframe)
        print(
            f"  {timeframe}: {len(series):,} candles in {len(runs):,} run(s), "
            f"longest {max((len(r) for r in runs), default=0):,}"
        )
    print()
    print("Report complete. The database was only read.")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
