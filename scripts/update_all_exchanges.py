"""Update the hourly candles of all exchanges (see src/data_collection/exchange_updater.py)."""

from src.data_collection.exchange_updater import update_all_exchanges


def main() -> None:
    update_all_exchanges()


if __name__ == "__main__":
    main()
