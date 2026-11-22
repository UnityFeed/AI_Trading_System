"""
Download the free external daily data (Coin Metrics community API: MVRV,
market cap, hash rate) into database/external_data.db. The first run
fetches the full history (since 2010); later runs only what is new.
Values already stored are never overwritten; changed values are logged as
revisions. Needs internet. The daily routine (and the app's button) also
does this.

Usage:
    python -m scripts.update_external_data
"""

import argparse
from pathlib import Path

from src.data_collection.external_data import ExternalDataStore, update_external_data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--external-db", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()
    store = ExternalDataStore(args.external_db) if args.external_db else ExternalDataStore()
    print("Updating external data from the Coin Metrics community API...")
    update_external_data(store)
    print(f"Saved in {store.path}")


if __name__ == "__main__":
    main()
