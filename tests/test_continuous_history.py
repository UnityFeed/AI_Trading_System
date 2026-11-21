import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from src.analysis.primary_history import (
    KRAKEN_PRIMARY_FROM,
    PRIMARY_LABEL,
    get_continuous_history,
)
from src.analysis.technical_indicators import IndicatorSettings, calculate_indicators
from src.analysis.timeframes import split_into_runs
from src.data_collection.market_data_repository import MarketDataRepository
from tests.helpers import hourly_candles


SWITCH = KRAKEN_PRIMARY_FROM
T0 = SWITCH - timedelta(hours=4)  # 2016-12-31 20:00


def at(hour: int):
    return T0 + timedelta(hours=hour)


class TestContinuousHistory(unittest.TestCase):
    """
    Hours 0-3 are 2016 (Bitstamp primary), hours 4-11 are 2017 (Kraken
    primary). Prices: bitstamp 1000+h, kraken 2000+h, coinbase 3000+h,
    so the source of every candle can be read from its close.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        folder = Path(self.temp_dir.name)

        self.repository = MarketDataRepository(folder / "test.db")
        self.exclusions_file = folder / "exclusions.csv"
        self.exclusions_file.write_text(
            "exchange,symbol,market,timeframe,timestamp,"
            "classification,evidence,analysis_action\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def store(self, exchange, base, skip=()):
        candles = hourly_candles(
            [base + h for h in range(12)],
            start=T0,
            exchange=exchange,
            skip_hours=set(skip),
        )
        self.repository.save_candles(candles=candles, timeframe="1h")

    def history(self):
        return get_continuous_history(
            repository=self.repository,
            start=T0,
            end=at(12),
            exclusions_file=self.exclusions_file,
        )

    def closes(self, history):
        return [c.close for c in history.candles]

    def test_kraken_gaps_are_filled_from_coinbase_first(self):

        self.store("bitstamp", 1000)
        self.store("kraken", 2000, skip=[6, 7])
        self.store("coinbase", 3000)

        history = self.history()

        self.assertEqual(
            self.closes(history),
            [1000, 1001, 1002, 1003, 2004, 2005, 3006, 3007,
             2008, 2009, 2010, 2011],
        )
        self.assertEqual(history.substituted_hours(), [at(6), at(7)])
        self.assertEqual(history.sources[at(6)], "coinbase")
        self.assertEqual(history.unfilled_hours, [])
        self.assertTrue(all(c.exchange == PRIMARY_LABEL for c in history.candles))

    def test_bitstamp_is_used_when_coinbase_is_missing_too(self):

        self.store("bitstamp", 1000)
        self.store("kraken", 2000, skip=[6])
        self.store("coinbase", 3000, skip=[6])

        history = self.history()

        self.assertEqual(history.sources[at(6)], "bitstamp")
        self.assertEqual(history.candles[6].close, 1006)

    def test_bitstamp_period_fills_from_coinbase_then_kraken(self):

        self.store("bitstamp", 1000, skip=[1, 2])
        self.store("kraken", 2000)
        self.store("coinbase", 3000, skip=[2])

        history = self.history()

        self.assertEqual(history.sources[at(1)], "coinbase")
        self.assertEqual(history.sources[at(2)], "kraken")
        self.assertEqual(history.primary_by_hour[at(2)], "bitstamp")

    def test_hours_no_exchange_has_stay_missing(self):

        self.store("bitstamp", 1000)
        self.store("kraken", 2000, skip=[6])
        self.store("coinbase", 3000, skip=[6])
        # Bitstamp hour 6 is zero-volume filler, so it is not clean either.
        filler = replace(
            hourly_candles([1006], start=at(6), exchange="bitstamp")[0],
            volume=0.0,
        )
        self.repository.save_candles(candles=[filler], timeframe="1h")

        history = self.history()

        self.assertEqual(history.unfilled_hours, [at(6)])
        self.assertEqual(len(history.candles), 11)
        self.assertEqual(
            [len(run) for run in split_into_runs(history.candles, "1h")],
            [6, 5],
        )

    def test_excluded_kraken_candle_is_replaced(self):

        self.store("bitstamp", 1000)
        self.store("kraken", 2000)
        self.store("coinbase", 3000)

        with self.exclusions_file.open("a", encoding="utf-8") as file:
            file.write(
                f"kraken,BTC/USD,crypto,1h,{at(8).isoformat()},"
                "suspect_source_value,test,exclude_pending_review\n"
            )

        history = self.history()

        self.assertEqual(history.sources[at(8)], "coinbase")

    def test_source_changes_record_price_jumps(self):

        self.store("bitstamp", 1000)
        self.store("kraken", 2000, skip=[6])
        self.store("coinbase", 3000)

        history = self.history()

        self.assertEqual(
            [(c.timestamp, c.from_exchange, c.to_exchange) for c in history.source_changes],
            [
                (at(4), "bitstamp", "kraken"),   # planned switch on 1 Jan 2017
                (at(6), "kraken", "coinbase"),
                (at(7), "coinbase", "kraken"),
            ],
        )

        into_coinbase = history.source_changes[1]
        self.assertAlmostEqual(into_coinbase.previous_close, 2005)
        self.assertAlmostEqual(into_coinbase.open, 3006)
        self.assertAlmostEqual(into_coinbase.jump_pct, (3006 / 2005 - 1) * 100)

        self.assertEqual(len(history.large_jumps(1.0)), 3)
        self.assertEqual(history.large_jumps(1000.0), [])

    def test_the_2017_switch_is_not_a_substitution(self):

        self.store("bitstamp", 1000)
        self.store("kraken", 2000)

        history = self.history()

        self.assertEqual(history.substituted_hours(), [])
        self.assertEqual(history.sources[at(3)], "bitstamp")
        self.assertEqual(history.sources[at(4)], "kraken")

    def test_periods_with_substitutes(self):

        self.store("bitstamp", 1000)
        self.store("kraken", 2000, skip=[6])
        self.store("coinbase", 3000)

        history = self.history()

        self.assertEqual(history.periods_with_substitutes("4h"), {at(4)})
        self.assertEqual(
            history.periods_with_substitutes("1d"), {SWITCH}
        )

    def test_indicators_run_across_filled_gaps_and_the_switch(self):

        self.store("bitstamp", 1000)
        self.store("kraken", 2000, skip=[5, 6])
        self.store("coinbase", 3000)

        history = self.history()
        rows = calculate_indicators(
            history.candles, "1h", IndicatorSettings(ema_periods=(3,))
        )

        self.assertEqual(len(split_into_runs(history.candles, "1h")), 1)
        self.assertIsNotNone(rows[5].values["ema_3"])  # no restart


if __name__ == "__main__":
    unittest.main()
