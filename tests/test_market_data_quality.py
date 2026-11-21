import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from src.analysis.market_data_quality import (
    DEFAULT_EXCLUSIONS_FILE,
    get_clean_candles,
    load_excluded_candle_keys,
)
from src.data_collection.market_data_repository import MarketDataRepository
from tests.helpers import BASE_TIME, hourly_candles


HEADER = (
    "exchange,symbol,market,timeframe,timestamp,"
    "classification,evidence,analysis_action\n"
)


class TestMarketDataQuality(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        folder = Path(self.temp_dir.name)

        self.repository = MarketDataRepository(folder / "test.db")
        self.exclusions_file = folder / "exclusions.csv"
        self.exclusions_file.write_text(HEADER, encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_exclusions(self, rows: list[str]) -> None:
        self.exclusions_file.write_text(
            HEADER + "".join(row + "\n" for row in rows),
            encoding="utf-8",
        )

    def save(self, candles, exchange="kraken"):
        self.repository.save_candles(candles=candles, timeframe="1h")

    def clean(self, exchange="kraken", **kwargs):
        return get_clean_candles(
            repository=self.repository,
            symbol="BTC/USD",
            market="crypto",
            timeframe="1h",
            start=BASE_TIME,
            end=BASE_TIME + timedelta(hours=24),
            exchange=exchange,
            exclusions_file=self.exclusions_file,
            **kwargs,
        )

    def test_excluded_candles_are_left_out(self):

        self.save(hourly_candles([100, 101, 102]))
        self.write_exclusions([
            "kraken,BTC/USD,crypto,1h,2026-11-14T01:00:00+00:00,"
            "suspect_source_value,test,exclude_pending_review",
        ])

        candles = self.clean()

        self.assertEqual(
            [c.timestamp for c in candles],
            [BASE_TIME, BASE_TIME + timedelta(hours=2)],
        )

    def test_rows_without_exclude_action_do_not_affect_analysis(self):

        self.save(hourly_candles([100, 101, 102]))
        self.write_exclusions([
            "kraken,BTC/USD,crypto,1h,2026-11-14T00:00:00+00:00,"
            "genuine_market_divergence,test,keep",
            "kraken,BTC/USD,crypto,1h,2026-11-14T01:00:00+00:00,"
            "suspect_thin_market_print,test,review_pending",
        ])

        self.assertEqual(len(self.clean()), 3)

    def test_exclusions_only_apply_to_their_own_exchange(self):

        self.save(hourly_candles([100, 101], exchange="kraken"))
        self.save(hourly_candles([100, 101], exchange="bitstamp"))
        self.write_exclusions([
            "kraken,BTC/USD,crypto,1h,2026-11-14T00:00:00+00:00,"
            "suspect_source_value,test,exclude_pending_review",
        ])

        self.assertEqual(len(self.clean(exchange="kraken")), 1)
        self.assertEqual(len(self.clean(exchange="bitstamp")), 2)

    def test_zero_volume_candles_are_skipped_by_default(self):

        candles = hourly_candles([100, 100, 102], exchange="bitstamp")
        candles[1] = replace(candles[1], volume=0.0)
        self.save(candles)

        clean = self.clean(exchange="bitstamp")

        self.assertEqual(
            [c.timestamp for c in clean],
            [BASE_TIME, BASE_TIME + timedelta(hours=2)],
        )

    def test_zero_volume_candles_can_be_kept_on_request(self):

        candles = hourly_candles([100, 100], exchange="bitstamp")
        candles[1] = replace(candles[1], volume=0.0)
        self.save(candles)

        clean = self.clean(exchange="bitstamp", exclude_zero_volume=False)

        self.assertEqual(len(clean), 2)

    def test_timestamps_with_other_offsets_are_matched_in_utc(self):

        self.save(hourly_candles([100, 101]))
        self.write_exclusions([
            "kraken,BTC/USD,crypto,1h,2026-11-14T02:00:00+01:00,"
            "suspect_source_value,test,exclude_pending_review",
        ])

        self.assertEqual(len(self.clean()), 1)

    def test_missing_columns_are_rejected(self):

        self.exclusions_file.write_text(
            "exchange,symbol,timestamp\n", encoding="utf-8"
        )

        with self.assertRaises(ValueError):
            load_excluded_candle_keys(self.exclusions_file)

    def test_naive_exclusion_timestamp_is_rejected(self):

        self.write_exclusions([
            "kraken,BTC/USD,crypto,1h,2026-11-14T00:00:00,"
            "suspect_source_value,test,exclude_pending_review",
        ])

        with self.assertRaises(ValueError):
            load_excluded_candle_keys(self.exclusions_file)


class TestProjectExclusionsFile(unittest.TestCase):
    """Guards the real data/quality/confirmed_anomalies.csv against typos."""

    def test_every_row_has_a_known_action_and_parses(self):

        import csv

        with DEFAULT_EXCLUSIONS_FILE.open(
            newline="", encoding="utf-8-sig"
        ) as file:
            rows = list(csv.DictReader(file))

        allowed = {"exclude_pending_review", "keep", "review_pending"}

        for line_number, row in enumerate(rows, start=2):
            with self.subTest(line=line_number):
                self.assertIn(row["analysis_action"], allowed)
                self.assertIn(
                    row["exchange"], {"kraken", "bitstamp", "coinbase"}
                )
                self.assertIsNone(row.get(None))  # no extra columns

        # Raises if any timestamp is invalid.
        load_excluded_candle_keys()


if __name__ == "__main__":
    unittest.main()
