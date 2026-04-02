"""Test tap respects the configured start_date.

NOTE: tap-ebay has no INCREMENTAL streams, so start_date filtering is not
applicable. This file is a stub kept for structural consistency.
"""
from base import TapEbayBaseTest


class TapEbayStartDateTest(TapEbayBaseTest):
    """Start date test — not applicable because no INCREMENTAL streams exist."""

    @staticmethod
    def name():
        return "tap_tester_tap_ebay_start_date_test"

    def streams_to_test(self):
        return self.expected_stream_names()

    @property
    def start_date_1(self):
        return "2015-03-25T00:00:00Z"

    @property
    def start_date_2(self):
        return "2017-01-25T00:00:00Z"
