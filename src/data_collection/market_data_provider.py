
from abc import ABC, abstractmethod
from datetime import datetime

from src.data_collection.market_data import MarketData


class MarketDataProvider(ABC):
    """
    Base interface for all external market data providers.
    """

    @abstractmethod
    def fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[MarketData]:
        """
        Fetch historical market candles.

        The returned candles must:
        - Use our standard MarketData format.
        - Be ordered from oldest to newest.
        - Have timestamps >= start and < end.
        """
        pass
