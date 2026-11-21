import unittest
from datetime import timedelta

from scripts.check_kraken_gaps import find_gaps
from tests.helpers import BASE_TIME


class TestFindGaps(unittest.TestCase):

    def test_gaps_are_reported_as_missing_ranges(self):

        hours = [BASE_TIME + timedelta(hours=h) for h in (0, 1, 4, 5, 7)]

        self.assertEqual(
            find_gaps(hours),
            [
                (BASE_TIME + timedelta(hours=2), BASE_TIME + timedelta(hours=4)),
                (BASE_TIME + timedelta(hours=6), BASE_TIME + timedelta(hours=7)),
            ],
        )

    def test_no_gaps(self):

        hours = [BASE_TIME + timedelta(hours=h) for h in range(3)]

        self.assertEqual(find_gaps(hours), [])
        self.assertEqual(find_gaps([]), [])


if __name__ == "__main__":
    unittest.main()
