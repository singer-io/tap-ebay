"""Test tap can replicate multiple pages of data for streams that use pagination."""
from tap_tester.base_suite_tests.pagination_test import PaginationTest

from base import TapEbayBaseTest


class TapEbayPaginationTest(PaginationTest, TapEbayBaseTest):
    """Ensure tap can replicate multiple pages of data for streams that support pagination.

    The eBay Fulfillment API returns up to 50 orders per page by default (API_LIMIT=50).
    This test verifies the tap correctly iterates through multiple pages.

    Note: The orders stream does not implement offset-based pagination in the current
    tap code — if the test environment contains ≤50 orders, add 'orders' to
    streams_to_exclude and open a follow-up ticket to add pagination support.
    """

    @staticmethod
    def name():
        return "tap_tester_tap_ebay_pagination_test"

    def streams_to_test(self):
        # Exclude streams that don't have enough test data to exceed one page.
        # If the eBay sandbox account has ≤50 orders, uncomment the exclusion below.
        streams_to_exclude = set()
        return self.expected_stream_names().difference(streams_to_exclude)
