"""
Step 2 report: build 4h and 1d candles from clean hourly data and check
the daily candles against each exchange's own published daily candles.

Part 1, per exchange: derive daily candles from that exchange's clean
hourly candles and compare them with the daily candles the same exchange
publishes (Kraken only publishes its last 720 days; Bitstamp and Coinbase
their full history). This needs internet access.

Part 2, primary history (Bitstamp before 2017, Kraken from 2017): how many
4h and 1d candles can be built per segment, and how many periods are
skipped because an hour is missing.

The database is only read; derived 4h/1d candles are built in memory and
not stored. Usage:
    python -m scripts.compare_daily_candles
    python -m scripts.compare_daily_candles path\\to\\other.db
"""

import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from src.analysis.daily_comparison import compare_daily_candles
from src.analysis.market_data_quality import get_clean_candles
from src.analysis.primary_history import get_primary_history
from src.analysis.timeframes import aggregate_hourly_candles, period_start
from src.data_collection.bitstamp_provider import BitstampProvider
from src.data_collection.coinbase_provider import CoinbaseProvider
from src.data_collection.kraken_provider import KrakenProvider
from src.data_collection.market_data_repository import MarketDataRepository
from src.data_collection.market_data_service import MarketDataService


SYMBOL = "BTC/USD"
MARKET = "crypto"
HISTORY_START = datetime(2013, 1, 1, tzinfo=timezone.utc)
WORST_DAYS_TO_SHOW = 5

# A derived daily price within this distance of the exchange's own value
# counts as a match (rounding and tiny late trade corrections).
MATCH_TOLERANCE_PCT = 0.01


def fmt_day(timestamp: datetime) -> str:
    return timestamp.strftime("%Y-%m-%d")


def per_year(timestamps) -> str:
    counts = Counter(timestamp.year for timestamp in timestamps)
    return ", ".join(f"{year}: {counts[year]}" for year in sorted(counts))


def compare_exchange(repository, provider, end: datetime) -> None:

    exchange = provider.exchange

    print(exchange.upper())
    print("-" * len(exchange))

    hourly = get_clean_candles(
        repository=repository,
        symbol=SYMBOL,
        market=MARKET,
        timeframe="1h",
        start=HISTORY_START,
        end=end,
        exchange=exchange,
    )

    if not hourly:
        print("No clean hourly candles stored.")
        print()
        return

    daily = aggregate_hourly_candles(hourly, "1d")

    print(f"Clean hourly candles: {len(hourly):,}")
    print(f"Complete days built:  {len(daily.candles):,}")
    print(f"Incomplete days skipped: {len(daily.incomplete_periods):,}")

    if daily.incomplete_periods:
        print(
            "  per year: "
            + per_year(p.start for p in daily.incomplete_periods)
        )

    try:
        reference = MarketDataService(provider).get_candles(
            symbol=SYMBOL,
            timeframe="1d",
            start=HISTORY_START,
            end=end,
        )
    except Exception as exc:
        print(f"Could not download {exchange} daily candles: {exc}")
        print()
        return

    if not reference:
        print("The exchange returned no daily candles.")
        print()
        return

    print(
        f"Exchange daily candles: {len(reference):,} "
        f"({fmt_day(reference[0].timestamp)} to "
        f"{fmt_day(reference[-1].timestamp)})"
    )

    # Compare only the period covered by both our hourly data and the
    # exchange's daily candles.
    overlap_start = max(
        period_start(hourly[0].timestamp, "1d"), reference[0].timestamp
    )
    overlap_end = min(hourly[-1].timestamp, reference[-1].timestamp)

    comparison = compare_daily_candles(
        [
            candle for candle in daily.candles
            if overlap_start <= candle.timestamp <= overlap_end
        ],
        [
            candle for candle in reference
            if overlap_start <= candle.timestamp <= overlap_end
        ],
    )
    matched = comparison.matched

    print(
        f"Compared period: {fmt_day(overlap_start)} to {fmt_day(overlap_end)}"
    )
    print(f"Days compared: {len(matched):,}")
    print(
        "Exchange days we could not build (missing/excluded/zero-volume "
        f"hours): {len(comparison.reference_only):,}"
    )
    print(
        "Days we built that the exchange does not publish: "
        f"{len(comparison.derived_only):,}"
    )

    if not matched:
        print()
        return

    for threshold in (MATCH_TOLERANCE_PCT, 0.1, 1.0):
        above = len(comparison.days_above(threshold))
        print(
            f"  days with an OHLC difference above {threshold}%: "
            f"{above:,} ({above / len(matched):.2%})"
        )

    volume_diffs = sorted(
        abs(day.volume_diff_pct)
        for day in matched
        if day.volume_diff_pct is not None
    )

    if volume_diffs:
        median = volume_diffs[len(volume_diffs) // 2]
        print(f"  median volume difference: {median:.4f}%")

    worst = [
        day for day in comparison.worst_days(WORST_DAYS_TO_SHOW)
        if day.max_price_diff_pct > MATCH_TOLERANCE_PCT
    ]

    if worst:
        print("  Largest differences (ours vs exchange):")

        for day in worst:
            ours, theirs = day.derived, day.reference
            print(
                f"    {fmt_day(day.timestamp)}  max {day.max_price_diff_pct:.3f}%"
            )
            print(
                f"      ours:     O={ours.open} H={ours.high} "
                f"L={ours.low} C={ours.close} V={ours.volume:.2f}"
            )
            print(
                f"      exchange: O={theirs.open} H={theirs.high} "
                f"L={theirs.low} C={theirs.close} V={theirs.volume:.2f}"
            )

    print()


def report_primary_history(repository, end: datetime) -> None:

    print("PRIMARY HISTORY (Bitstamp before 2017, Kraken from 2017)")
    print("=========================================================")

    segments = get_primary_history(
        repository=repository,
        start=HISTORY_START,
        end=end,
    )

    for segment in segments:

        print(
            f"{segment.exchange}: {fmt_day(segment.start)} to "
            f"{fmt_day(segment.end)} (end exclusive)"
        )
        print(f"  clean hourly candles: {len(segment.candles):,}")

        for timeframe in ("4h", "1d"):
            result = aggregate_hourly_candles(segment.candles, timeframe)
            print(
                f"  {timeframe}: {len(result.candles):,} complete, "
                f"{len(result.incomplete_periods):,} skipped"
            )

    print()


def main(db_path: Path | None = None) -> None:

    repository = MarketDataRepository(db_path) if db_path else MarketDataRepository()

    # Only fully completed UTC days.
    end = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    print("DAILY CANDLE CHECK")
    print("==================")
    print(f"Symbol: {SYMBOL}")
    print(f"Days up to (not including): {fmt_day(end)}")
    print()

    for provider in (KrakenProvider(), BitstampProvider(), CoinbaseProvider()):
        compare_exchange(repository, provider, end)

    report_primary_history(repository, end)

    print("Check complete. The database was only read.")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
