import sqlite3
from contextlib import closing
from pathlib import Path
from statistics import median


CROSS_EXCHANGE_THRESHOLD_PCT = 5.0
INTRACANDLE_RANGE_THRESHOLD_PCT = 20.0
MAX_ROWS_TO_DISPLAY = 100


def main():

    project_root = Path(__file__).resolve().parents[1]
    db_path = project_root / "database" / "market_data.db"

    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")

    with closing(sqlite3.connect(db_path)) as connection:
        rows = connection.execute("""
            SELECT
                exchange,
                timestamp,
                open,
                high,
                low,
                close,
                volume
            FROM market_candles
            WHERE symbol = 'BTC/USD'
            AND market = 'crypto'
            AND timeframe = '1h'
            ORDER BY timestamp, exchange
        """).fetchall()

    candles_by_timestamp = {}

    for row in rows:
        (
            exchange,
            timestamp,
            open_price,
            high,
            low,
            close,
            volume,
        ) = row

        candles_by_timestamp.setdefault(timestamp, {})[exchange] = {
            "open": float(open_price),
            "high": float(high),
            "low": float(low),
            "close": float(close),
            "volume": float(volume),
        }

    anomalies = []

    for timestamp, exchange_candles in candles_by_timestamp.items():

        for exchange, candle in exchange_candles.items():

            range_pct = (
                (candle["high"] - candle["low"])
                / candle["open"]
                * 100.0
            )

            peer_closes = [
                other_candle["close"]
                for other_exchange, other_candle
                in exchange_candles.items()
                if other_exchange != exchange
            ]

            peer_median = median(peer_closes) if peer_closes else None
            peer_difference_pct = None

            if peer_median is not None and peer_median > 0:
                peer_difference_pct = (
                    abs(candle["close"] - peer_median)
                    / peer_median
                    * 100.0
                )

            reasons = []

            if range_pct >= INTRACANDLE_RANGE_THRESHOLD_PCT:
                reasons.append("wide candle range")

            if (
                peer_difference_pct is not None
                and peer_difference_pct >= CROSS_EXCHANGE_THRESHOLD_PCT
            ):
                reasons.append("close differs from peer median")

            if reasons:
                severity = max(
                    range_pct / INTRACANDLE_RANGE_THRESHOLD_PCT,
                    (
                        peer_difference_pct
                        / CROSS_EXCHANGE_THRESHOLD_PCT
                        if peer_difference_pct is not None
                        else 0.0
                    ),
                )

                anomalies.append({
                    "timestamp": timestamp,
                    "exchange": exchange,
                    "candle": candle,
                    "range_pct": range_pct,
                    "peer_median": peer_median,
                    "peer_difference_pct": peer_difference_pct,
                    "peer_count": len(peer_closes),
                    "reasons": reasons,
                    "severity": severity,
                })

    anomalies.sort(
        key=lambda item: item["severity"],
        reverse=True,
    )

    wide_range_count = sum(
        "wide candle range" in item["reasons"]
        for item in anomalies
    )
    peer_difference_count = sum(
        "close differs from peer median" in item["reasons"]
        for item in anomalies
    )

    print("BTC/USD HOURLY DATA ANOMALY SCAN")
    print("================================")
    print(f"Database: {db_path}")
    print(f"Candles scanned: {len(rows):,}")
    print(f"Flagged candle records: {len(anomalies):,}")
    print(f"Wide candle ranges: {wide_range_count:,}")
    print(f"Close differs from peer median: {peer_difference_count:,}")
    print()
    print("SCREENING THRESHOLDS")
    print("--------------------")
    print(
        "Candle range: "
        f"{INTRACANDLE_RANGE_THRESHOLD_PCT:.1f}% of open"
    )
    print(
        "Peer close difference: "
        f"{CROSS_EXCHANGE_THRESHOLD_PCT:.1f}%"
    )
    print()
    print("LARGEST CANDIDATES")
    print("------------------")

    if not anomalies:
        print("No candles met the screening thresholds.")

    for item in anomalies[:MAX_ROWS_TO_DISPLAY]:
        candle = item["candle"]

        print()
        print(
            f"{item['timestamp']} | {item['exchange']} | "
            f"{', '.join(item['reasons'])}"
        )
        print(
            f"  OHLC: O={candle['open']} H={candle['high']} "
            f"L={candle['low']} C={candle['close']} "
            f"V={candle['volume']}"
        )
        print(f"  High-low range: {item['range_pct']:.3f}% of open")

        if item["peer_median"] is not None:
            print(
                f"  Other-exchange median close: "
                f"{item['peer_median']:.8f} "
                f"(from {item['peer_count']} exchange(s))"
            )
            print(
                f"  Close difference from median: "
                f"{item['peer_difference_pct']:.3f}%"
            )

    if len(anomalies) > MAX_ROWS_TO_DISPLAY:
        print()
        print(
            f"Only the largest {MAX_ROWS_TO_DISPLAY} candidates "
            f"are displayed."
        )

    print()
    print("Scan complete. The database was only read.")


if __name__ == "__main__":
    main()