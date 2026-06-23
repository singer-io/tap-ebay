"""Test that running the tap with all streams and fields selected replicates all fields."""
from tap_tester.base_suite_tests.all_fields_test import AllFieldsTest

from base import TapEbayBaseTest


# Declare known fields that exist in the schema but are NOT returned by the
# test-environment API (e.g. features not enabled in eBay sandbox accounts).
# Start empty — populate after a first test run reveals schema/data mismatches.
KNOWN_MISSING_FIELDS = {
    # Observed as intermittently absent in sandbox order payloads.
    "orders": {
        "program",
        "buyerCheckoutNotes",
        "totalMarketplaceFee",
        "ebayCollectAndRemitTaxes",
        "salesRecordReference",
    },
}


class TapEbayAllFields(AllFieldsTest, TapEbayBaseTest):
    """Ensure running the tap with all streams and fields selected results in
    the replication of all fields present in the schema."""

    MISSING_FIELDS = KNOWN_MISSING_FIELDS

    @staticmethod
    def name():
        return "tap_tester_tap_ebay_all_fields_test"

    def streams_to_test(self):
        # Exclude streams with no test data or limited API access in the test environment
        streams_to_exclude = set()
        return self.expected_stream_names().difference(streams_to_exclude)
