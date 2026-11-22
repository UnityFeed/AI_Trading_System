"""
Record Kraken's order book and buy/sell order flow from now on, into
database/order_flow.db (see src/data_collection/order_flow.py). Free, no
key. Normally started by double-clicking start_recorder.bat.

While it runs: an order-book snapshot every minute, and every 15 minutes
the completed hours of trade flow (buy vs sell volume, exact VWAP) are
filled in. When it was off, the trade flow is caught up afterwards (Kraken
keeps all trades); the order book cannot be (missed snapshots are gone).

Usage:
    python -m scripts.record_order_flow             (run until Ctrl+C)
    python -m scripts.record_order_flow --once      (one snapshot + catch up, then stop)
    python -m scripts.record_order_flow --days 30   (first run: fill trade flow 30 days back)
"""

import argparse
from datetime import timedelta
from pathlib import Path

from src.data_collection.order_flow import OrderFlowStore, collect_trade_flow, record_book, run_recorder


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="one snapshot and catch-up, then stop")
    parser.add_argument("--days", type=int, default=7, help="first run only: trade flow this many days back")
    parser.add_argument("--db", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    store = OrderFlowStore(args.db) if args.db else OrderFlowStore()
    print(f"Recording into {store.path}")
    if store.last_flow_hour() is None:
        print(f"First run: filling trade flow {args.days} days back (about 100-150 requests per day)...")
        while collect_trade_flow(store, first_start=timedelta(days=args.days)) > 0:
            pass

    if args.once:
        summary = record_book(store)
        print(f"Order book: spread {summary['spread_pct']:.4f}%, imbalance within 1% {summary['imbalance_1']:+.2f}")
        while collect_trade_flow(store) > 0:
            pass
        print(f"{store.book_count():,} book snapshots, {len(store.flows()):,} hours of trade flow stored.")
        return

    print("Recording. Keep this window open; close it (or press Ctrl+C) to stop.")
    try:
        run_recorder(store)
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    main()
