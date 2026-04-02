"""Test tap bookmark behaviour.

NOTE: All tap-ebay streams use FULL_TABLE replication.
Bookmark tests only apply to INCREMENTAL streams and are therefore skipped.
"""
import unittest

from base import TapEbayBaseTest


class TapEbayBookMarkTest(TapEbayBaseTest):
    """Test tap sets a bookmark and respects it for the next sync of a stream.

    Skipped because all streams use FULL_TABLE replication.
    Bookmark tests only apply to INCREMENTAL streams.
    """

    @staticmethod
    def name():
        return "tap_tester_tap_ebay_bookmark_test"

    @unittest.skip("All streams use FULL_TABLE replication — bookmark test not applicable")
    def test_run(self):
        pass
