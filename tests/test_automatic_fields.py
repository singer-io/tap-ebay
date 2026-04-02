"""Test that with no fields selected, automatic fields are still replicated."""
from tap_tester.base_suite_tests.automatic_fields_test import MinimumSelectionTest

from base import TapEbayBaseTest


class TapEbayAutomaticFields(MinimumSelectionTest, TapEbayBaseTest):
    """Test that with no fields selected for a stream, automatic fields
    (primary keys) are still replicated."""

    @staticmethod
    def name():
        return "tap_tester_tap_ebay_automatic_fields_test"

    def streams_to_test(self):
        # Exclude streams with known missing test data in the sandbox environment
        streams_to_exclude = set()
        return self.expected_stream_names().difference(streams_to_exclude)
