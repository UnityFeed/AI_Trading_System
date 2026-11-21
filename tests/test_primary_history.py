import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.analysis.indicators import calculate_hourly_sma
from src.analysis.primary_history import (
    KRAKEN_PRIMARY_FROM,
    get_primary_history,
)
from src.data_collection.market_data_repository import MarketDataRepository
from tests.helpers import hourly_candles


SWITCH = KRAKEN_PRIMARY_FROM
BEFORE = SWITCH - timedelta(hours=3)  # 2016-12-31 21:00


class TestPrimaryHistory(unittest.TestCase):

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

        # All three exchanges have 6 hours around the switch:
        # 21:00, 22:00, 23:00 on 31 Dec 2016 and 00:00-02:00 on 1 Jan 2017.
        for exchange, base in (
            ("bitstamp", 1000),
            ("kraken", 2000),
            ("coinbase", 3000),
        ):
            self.repository.save_candles(
                candles=hourly_candles(
                    [base + i for i in range(6)],
                    start=BEFORE,
                    exchange=exchange,
                ),
                timeframe="1h",
            )

    def tearDown(self):
        self.temp_dir.cleanup()

    def history(self, start, end):
        return get_primary_history(
            repository=self.repository,
            start=start,
            end=end,
            exclusions_file=self.exclusions_file,
        )

    def test_bitstamp_before_switch_and_kraken_from_switch(self):

        segments = self.history(BEFORE, BEFORE + timedelta(hours=6))

        self.assertEqual([s.exchange for s in segments], ["bitstamp", "kraken"])

        bitstamp, kraken = segments

        self.assertEqual([c.close for c in bitstamp.candles], [1000, 1001, 1002])
        self.assertEqual([c.close for c in kraken.candles], [2003, 2004, 2005])

        self.assertEqual(bitstamp.end, SWITCH)
        self.assertEqual(kraken.start, SWITCH)
        self.assertTrue(all(c.exchange == "bitstamp" for c in bitstamp.candles))
        self.assertTrue(all(c.exchange == "kraken" for c in kraken.candles))

    def test_coinbase_is_never_used(self):

        segments = self.history(BEFORE, BEFORE + timedelta(hours=6))

        for segment in segments:
            for candle in segment.candles:
                self.assertNotEqual(candle.exchange, "coinbase")

    def test_window_after_switch_returns_only_kraken(self):

        segments = self.history(SWITCH, SWITCH + timedelta(hours=3))

        self.assertEqual([s.exchange for s in segments], ["kraken"])
        self.assertEqual(len(segments[0].candles), 3)

    def test_window_before_switch_returns_only_bitstamp(self):

        segments = self.history(BEFORE, SWITCH)

        self.assertEqual([s.exchange for s in segments], ["bitstamp"])
        self.assertEqual(len(segments[0].candles), 3)

    def test_segments_contain_clean_candles_only(self):

        # A zero-volume Bitstamp filler candle at 22:00 becomes a gap.
        filler = replace(
            hourly_candles([1001], start=BEFORE + timedelta(hours=1),
                           exchange="bitstamp")[0],
            volume=0.0,
        )
        self.repository.save_candles(candles=[filler], timeframe="1h")

        # A Kraken candle on the exclusion list is left out as well.
        with self.exclusions_file.open("a", encoding="utf-8") as file:
            file.write(
                "kraken,BTC/USD,crypto,1h,2017-01-01T01:00:00+00:00,"
                "suspect_source_value,test,exclude_pending_review\n"
            )

        bitstamp, kraken = self.history(BEFORE, BEFORE + timedelta(hours=6))

        self.assertEqual([c.close for c in bitstamp.candles], [1000, 1002])
        self.assertEqual([c.close for c in kraken.candles], [2003, 2005])

    def test_indicators_run_per_segment_and_reset_at_switch(self):

        segments = self.history(BEFORE, BEFORE + timedelta(hours=6))

        averages = [
            calculate_hourly_sma(segment.candles, period_hours=3)
            for segment in segments
        ]

        # Each segment has exactly 3 hours, so one SMA each and none
        # whose window spans the two exchanges.
        self.assertEqual([len(a) for a in averages], [1, 1])
        self.assertEqual(averages[0][0].exchange, "bitstamp")
        self.assertEqual(averages[1][0].exchange, "kraken")

    def test_non_utc_window_is_converted(self):

        plus_one = timezone(timedelta(hours=1))
        start = datetime(2017, 1, 1, 1, 0, tzinfo=plus_one)  # = SWITCH

        segments = self.history(start, start + timedelta(hours=3))

        self.assertEqual([s.exchange for s in segments], ["kraken"])
        self.assertEqual(segments[0].start, SWITCH)

    def test_invalid_windows_are_rejected(self):

        with self.assertRaises(ValueError):
            self.history(datetime(2017, 1, 1), SWITCH + timedelta(hours=1))

        with self.assertRaises(ValueError):
            self.history(SWITCH, SWITCH)


if __name__ == "__main__":
    unittest.main()
