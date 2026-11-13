
from dataclasses import dataclass
from datetime import datetime


@dataclass
class MarketData:
    symbol: str
    market: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
