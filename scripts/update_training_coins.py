"""
Download the hourly history of the AI's training coins (ETH, BNB, XRP, SOL,
TRX: the five largest coins after BTC) from Binance's public market data
into database/training_coins.db. Pure training data for the AI: never
shown or traded. The first run downloads everything since 2017 (a few
minutes); later runs only what is new. The training session
(python -m scripts.train_engine) runs this first by itself.

Usage:
    python -m scripts.update_training_coins
"""

import argparse
from pathlib import Path

from src.data_collection.market_data_repository import MarketDataRepository
from src.data_collection.training_coins import DEFAULT_PATH, coin_histories, update_training_coins


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()
    repository = MarketDataRepository(args.db or DEFAULT_PATH)
    print("Updating the AI's training coins from Binance (public market data)...")
    update_training_coins(repository)
    for coin, history in coin_histories(repository).items():
        print(f"  {coin}: {len(history.candles):,} hourly candles from {history.candles[0].timestamp:%Y-%m-%d}")
    print(f"Saved in {repository.db_path}")


if __name__ == "__main__":
    main()
