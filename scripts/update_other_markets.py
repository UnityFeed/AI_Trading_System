"""
Download the daily history of the other markets the AI learns from:
S&P 500, Nasdaq 100 (NAS100), Dow Jones 30 (US30), gold and silver, from
Yahoo Finance (free, no key) into database/other_markets.db. The first run
fetches the full history (decades); later runs add what is new. Stored
days are never overwritten (changes are noted as revisions). Needs
internet. The daily routine and the app's button also do this.

Usage:
    python -m scripts.update_other_markets
"""

import argparse
from pathlib import Path

from src.data_collection.other_markets import MARKETS, OtherMarketsStore, update_other_markets


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()
    store = OtherMarketsStore(args.db) if args.db else OtherMarketsStore()
    print("Updating other markets from Yahoo Finance...")
    update_other_markets(store)
    for name in MARKETS:
        closes = store.closes(name)
        if closes:
            first, last = min(closes), max(closes)
            print(f"  {name:<7} {len(closes):>6,} days  {first} to {last}  last close {closes[last]:,.2f}")
    print(f"Saved in {store.path}")


if __name__ == "__main__":
    main()
