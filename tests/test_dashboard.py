import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.analysis.primary_history import get_continuous_history
from src.data_collection.market_data_repository import MarketDataRepository
from src.paper_trading.store import Fill, PaperTradingStore
from src.reporting.dashboard import account_equity, gather, market_reading, nice_ticks, render
from tests.helpers import hourly_candles


START = datetime(2026, 1, 1, tzinfo=timezone.utc)


class TestDashboardPieces(unittest.TestCase):

    def test_market_reading_in_plain_words(self):

        readings = {topic: verdict for topic, verdict, _ in market_reading(
            {"ema_50": 110, "ema_200": 100, "macd": 2, "macd_signal": 1, "rsi_14": 25,
             "bb_upper": 120, "bb_lower": 100, "atr_14": 3, "relative_volume_20": 1.5},
            close=105,
        )}

        self.assertEqual(readings["Long trend"], "Up")
        self.assertEqual(readings["Price vs EMA 200"], "Above")
        self.assertEqual(readings["Momentum (MACD)"], "Rising")
        self.assertEqual(readings["RSI 14"], "Oversold")
        self.assertEqual(readings["Bollinger position"], "25%")
        self.assertEqual(readings["Volatility (ATR 14)"], "2.9%")

    def test_missing_values_are_left_out(self):

        self.assertEqual(market_reading({}, close=100), [])

    def test_nice_ticks(self):

        self.assertEqual(nice_ticks(0, 100), [0, 20, 40, 60, 80, 100])
        self.assertEqual(nice_ticks(58_000, 106_000), [60_000, 70_000, 80_000, 90_000, 100_000])

    def test_account_equity_follows_fills(self):

        days = [
            replace(c, timestamp=START + timedelta(days=i), open=o, close=o)
            for i, (c, o) in enumerate(zip(hourly_candles([1] * 3), [100, 110, 121]))
        ]
        account = type("A", (), {"start_candle": START, "starting_cash": 1000.0})()
        fills = [Fill(1, 1, START + timedelta(days=1), "buy", 110, 0, 1000 / 110, 0.0, 1000 / 110)]

        points = account_equity(account, fills, days)

        self.assertEqual([round(p[1], 2) for p in points], [1000.0, 1000.0, 1100.0])
        self.assertEqual([round(p[2], 2) for p in points], [1000.0, 1100.0, 1210.0])


class TestDashboardPage(unittest.TestCase):

    def test_page_builds_with_and_without_an_account(self):

        with tempfile.TemporaryDirectory() as folder:
            repository = MarketDataRepository(Path(folder) / "market.db")
            closes = [100 + (i % 40) for i in range(24 * 60)]
            for exchange in ("kraken", "coinbase"):
                repository.save_candles(
                    candles=hourly_candles(closes, start=START, exchange=exchange), timeframe="1h"
                )
            history = get_continuous_history(repository, START, START + timedelta(days=60))
            store = PaperTradingStore(Path(folder) / "paper.db")

            page = render(gather(repository, history, store, now=START + timedelta(days=60)))
            self.assertIn("No paper account yet", page)
            self.assertIn("<h2>Your data</h2>", page)

            store.create_account("test", "1d", 10_000.0, START)
            page = render(gather(repository, history, store, now=START + timedelta(days=60)))
            self.assertIn("Account value", page)
            self.assertIn('id="price"', page)
            self.assertIn("python -m scripts.daily_run", page)


if __name__ == "__main__":
    unittest.main()
