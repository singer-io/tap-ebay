"""Base test case for tap-ebay integration tests."""
import os

from tap_tester.base_suite_tests.base_case import BaseCase


class TapEbayBaseTest(BaseCase):
    """Setup expectations for test sub classes.

    Metadata describing streams. A bunch of shared methods that are used
    in tap-tester tests. Shared tap-specific methods (as needed).
    """
    start_date = "2019-01-01T00:00:00Z"

    @staticmethod
    def tap_name():
        """The name of the tap."""
        return "tap-ebay"

    @staticmethod
    def get_type():
        """The Stitch connection type slug."""
        return "platform.ebay"

    def setUp(self, **kwargs):
        missing = [
            v for v in [
                "TAP_EBAY_CLIENT_ID",
                "TAP_EBAY_CLIENT_SECRET",
                "TAP_EBAY_REFRESH_TOKEN",
                "TAP_EBAY_SCOPE",
            ]
            if not os.getenv(v)
        ]
        if missing:
            raise Exception(f"Missing required environment variables: {missing}")

    def get_properties(self, original: bool = True):
        """Configuration properties required for the tap."""
        return_value = {
            "start_date": self.start_date,
        }
        if original:
            return return_value

        return_value["start_date"] = self.start_date
        return return_value

    @staticmethod
    def get_credentials():
        """Authentication information for the test account.

        Values are read from environment variables — never hardcode credentials.
        """
        return {
            "client_id":     os.getenv("TAP_EBAY_CLIENT_ID"),
            "client_secret": os.getenv("TAP_EBAY_CLIENT_SECRET"),
            "refresh_token": os.getenv("TAP_EBAY_REFRESH_TOKEN"),
            "scope":         os.getenv("TAP_EBAY_SCOPE"),
            "sandbox":       True,
        }

    @classmethod
    def expected_metadata(cls):
        """The expected streams and metadata about the streams."""
        return {
            "orders": {
                cls.PRIMARY_KEYS:        {"orderId"},
                cls.REPLICATION_METHOD:  cls.FULL_TABLE,
                cls.REPLICATION_KEYS:    set(),
                cls.OBEYS_START_DATE:    False,
                cls.API_LIMIT:           50,
            },
        }
