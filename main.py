
from src.data_collection.kraken_provider import KrakenProvider
from src.data_collection.market_data_service import MarketDataService
from src.data_collection.market_data_repository import MarketDataRepository
from src.data_collection.market_data_collector import MarketDataCollector


def main():

    print("================================")
    print("       AI TRADING SYSTEM")
    print("================================")
    print("Environment: Ready")
    print("Trading mode: Paper Trading")
    print("Live trading: Disabled")
    print()

    try:
        provider = KrakenProvider()
        service = MarketDataService(provider)
        repository = MarketDataRepository()

        collector = MarketDataCollector(
            market_data_service=service,
            repository=repository,
        )

        print("Market data provider: Kraken")
        print("Database: Connected")
        print("Collector: Initialized")
        print("System status: Ready")

    except Exception as exc:
        print(f"System status: Initialization failed")
        print(f"Error: {exc}")
        raise


if __name__ == "__main__":
    main()
