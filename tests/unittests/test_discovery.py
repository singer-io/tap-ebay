"""
Unit tests for tap_ebay discovery — catalog generation, stream metadata, and selection logic.
"""
import json
import sys
import unittest
from io import StringIO
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

from singer import metadata as meta

from tap_ebay import EbayRunner
from tap_ebay.client import EbayForbiddenError
from tap_ebay.streams import AVAILABLE_STREAMS
from tap_ebay.streams.base import Base, is_stream_selected
from tap_ebay.streams.orders import OrdersStream


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_catalog_entry(stream_name, selected=None, inclusion='available'):
    """Create a mock catalog stream entry with the given metadata state."""
    mdata = meta.new()
    mdata = meta.write(mdata, (), 'inclusion', inclusion)
    if selected is not None:
        mdata = meta.write(mdata, (), 'selected', selected)
    entry = MagicMock()
    entry.stream = stream_name
    entry.metadata = meta.to_list(mdata)
    return entry


def _make_runner_args(config=None):
    args = MagicMock()
    args.config = config or {'start_date': '2024-01-01T00:00:00Z'}
    args.state = {}
    args.catalog = None
    return args


# ---------------------------------------------------------------------------
# is_stream_selected
# ---------------------------------------------------------------------------

class TestIsStreamSelected(unittest.TestCase):
    """Tests for streams.base.is_stream_selected()."""

    def test_explicit_selected_true_returns_true(self):
        """selected=True in metadata means the stream is selected."""
        entry = _make_catalog_entry('orders', selected=True)
        self.assertTrue(is_stream_selected(entry))

    def test_explicit_selected_false_returns_false(self):
        """selected=False in metadata means the stream is not selected."""
        entry = _make_catalog_entry('orders', selected=False)
        self.assertFalse(is_stream_selected(entry))

    def test_unsupported_inclusion_returns_false(self):
        """Streams with inclusion=unsupported are never selected."""
        entry = _make_catalog_entry('orders', inclusion='unsupported')
        self.assertFalse(is_stream_selected(entry))

    def test_automatic_inclusion_without_selected_returns_true(self):
        """inclusion=automatic with no explicit selected flag means selected."""
        entry = _make_catalog_entry('orders', inclusion='automatic')
        self.assertTrue(is_stream_selected(entry))

    def test_available_inclusion_without_selected_returns_false(self):
        """inclusion=available with no explicit selected flag means not selected."""
        entry = _make_catalog_entry('orders', inclusion='available')
        self.assertFalse(is_stream_selected(entry))

    def test_selected_false_overrides_automatic_inclusion(self):
        """Explicit selected=False takes precedence over inclusion=automatic."""
        entry = _make_catalog_entry('orders', selected=False, inclusion='automatic')
        self.assertFalse(is_stream_selected(entry))

    def test_selected_true_overrides_available_inclusion(self):
        """Explicit selected=True takes precedence over inclusion=available."""
        entry = _make_catalog_entry('orders', selected=True, inclusion='available')
        self.assertTrue(is_stream_selected(entry))


# ---------------------------------------------------------------------------
# OrdersStream class attributes
# ---------------------------------------------------------------------------

class TestOrdersStreamAttributes(unittest.TestCase):
    """Tests for OrdersStream static attributes and property methods."""

    def test_table_name_is_orders(self):
        """TABLE must equal 'orders'."""
        self.assertEqual(OrdersStream.TABLE, 'orders')

    def test_key_properties_contains_order_id(self):
        """orderId is declared as the primary key."""
        self.assertIn('orderId', OrdersStream.KEY_PROPERTIES)

    def test_api_method_is_get(self):
        """API_METHOD must be GET."""
        self.assertEqual(OrdersStream.API_METHOD, 'GET')

    def test_path_property_is_correct(self):
        """path property returns the eBay fulfillment API path."""
        stream = OrdersStream({'start_date': '2024-01-01T00:00:00Z'}, {}, None, None)
        self.assertEqual(stream.path, '/sell/fulfillment/v1/order')

    def test_get_url_starts_with_ebay_api_base(self):
        """get_url() returns a URL with scheme https and hostname api.ebay.com."""
        stream = OrdersStream({'start_date': '2024-01-01T00:00:00Z'}, {}, None, None)
        parsed = urlparse(stream.get_url())
        self.assertEqual(parsed.scheme, 'https')
        self.assertEqual(parsed.hostname, 'api.ebay.com')

    def test_get_url_contains_fulfillment_path(self):
        """get_url() includes the fulfillment v1 order path."""
        stream = OrdersStream({'start_date': '2024-01-01T00:00:00Z'}, {}, None, None)
        self.assertIn('/sell/fulfillment/v1/order', stream.get_url())

    def test_matches_catalog_true_for_orders(self):
        """matches_catalog() returns True when catalog stream name is 'orders'."""
        entry = MagicMock()
        entry.stream = 'orders'
        self.assertTrue(OrdersStream.matches_catalog(entry))

    def test_matches_catalog_false_for_other_stream(self):
        """matches_catalog() returns False when stream name does not match."""
        entry = MagicMock()
        entry.stream = 'products'
        self.assertFalse(OrdersStream.matches_catalog(entry))

    def test_requirements_met_when_requires_is_empty(self):
        """requirements_met() returns True when REQUIRES list is empty."""
        catalog = MagicMock()
        catalog.streams = []
        self.assertTrue(OrdersStream.requirements_met(catalog))


# ---------------------------------------------------------------------------
# Catalog generation
# ---------------------------------------------------------------------------

class TestOrdersStreamGenerateCatalog(unittest.TestCase):
    """Tests for OrdersStream.generate_catalog()."""

    def setUp(self):
        self.stream = OrdersStream({'start_date': '2024-01-01T00:00:00Z'}, {}, None, None)

    def test_generate_catalog_returns_a_list(self):
        """generate_catalog() returns a list."""
        catalog = self.stream.generate_catalog()
        self.assertIsInstance(catalog, list)

    def test_generate_catalog_returns_single_entry(self):
        """generate_catalog() produces exactly one catalog entry."""
        catalog = self.stream.generate_catalog()
        self.assertEqual(len(catalog), 1)

    def test_catalog_entry_tap_stream_id_is_orders(self):
        """tap_stream_id in catalog entry equals 'orders'."""
        catalog = self.stream.generate_catalog()
        self.assertEqual(catalog[0]['tap_stream_id'], 'orders')

    def test_catalog_entry_stream_name_is_orders(self):
        """stream in catalog entry equals 'orders'."""
        catalog = self.stream.generate_catalog()
        self.assertEqual(catalog[0]['stream'], 'orders')

    def test_catalog_entry_key_properties_contains_order_id(self):
        """orderId is listed in key_properties of the catalog entry."""
        catalog = self.stream.generate_catalog()
        self.assertIn('orderId', catalog[0]['key_properties'])

    def test_catalog_entry_has_schema_with_properties(self):
        """schema is present in catalog entry and has a properties dict."""
        catalog = self.stream.generate_catalog()
        self.assertIn('schema', catalog[0])
        self.assertIn('properties', catalog[0]['schema'])

    def test_catalog_entry_has_metadata_list(self):
        """metadata in catalog entry is a list."""
        catalog = self.stream.generate_catalog()
        self.assertIsInstance(catalog[0]['metadata'], list)

    def test_key_property_has_automatic_inclusion(self):
        """orderId (key property) has inclusion=automatic in metadata."""
        catalog = self.stream.generate_catalog()
        mdata = meta.to_map(catalog[0]['metadata'])
        inclusion = meta.get(mdata, ('properties', 'orderId'), 'inclusion')
        self.assertEqual(inclusion, 'automatic')

    def test_non_key_property_has_available_inclusion(self):
        """buyer (non-key) has inclusion=available in metadata."""
        catalog = self.stream.generate_catalog()
        mdata = meta.to_map(catalog[0]['metadata'])
        inclusion = meta.get(mdata, ('properties', 'buyer'), 'inclusion')
        self.assertEqual(inclusion, 'available')

    def test_root_metadata_has_available_inclusion(self):
        """Root-level inclusion in stream metadata is 'available'."""
        catalog = self.stream.generate_catalog()
        mdata = meta.to_map(catalog[0]['metadata'])
        root_inclusion = meta.get(mdata, (), 'inclusion')
        self.assertEqual(root_inclusion, 'available')


# ---------------------------------------------------------------------------
# EbayRunner.do_discover()
# ---------------------------------------------------------------------------

class TestEbayRunnerDiscover(unittest.TestCase):
    """Tests for EbayRunner.do_discover() — catalog discovery output."""

    def _run_discover(self, available_streams=None):
        args = _make_runner_args()
        streams = AVAILABLE_STREAMS if available_streams is None else available_streams
        runner = EbayRunner(args, MagicMock(), streams)
        captured = StringIO()
        with patch('sys.stdout', captured):
            runner.do_discover()
        return json.loads(captured.getvalue())

    def test_do_discover_outputs_valid_json(self):
        """do_discover() writes valid JSON to stdout."""
        catalog = self._run_discover()
        self.assertIsInstance(catalog, dict)

    def test_do_discover_output_has_streams_key(self):
        """do_discover() output contains a 'streams' key."""
        catalog = self._run_discover()
        self.assertIn('streams', catalog)

    def test_do_discover_streams_is_a_list(self):
        """streams value in discover output is a list."""
        catalog = self._run_discover()
        self.assertIsInstance(catalog['streams'], list)

    def test_do_discover_includes_orders_stream(self):
        """do_discover() emits at least the 'orders' stream."""
        catalog = self._run_discover()
        stream_names = [s['stream'] for s in catalog['streams']]
        self.assertIn('orders', stream_names)

    def test_do_discover_orders_entry_has_key_properties(self):
        """orders catalog entry from discover contains key_properties."""
        catalog = self._run_discover()
        orders = next(s for s in catalog['streams'] if s['stream'] == 'orders')
        self.assertIn('key_properties', orders)
        self.assertIn('orderId', orders['key_properties'])

    def test_do_discover_empty_streams_list(self):
        """do_discover() with no available streams outputs empty streams list."""
        catalog = self._run_discover(available_streams=[])
        self.assertEqual(catalog['streams'], [])


# ---------------------------------------------------------------------------
# Access check exclusion during discovery
# ---------------------------------------------------------------------------

class TestCheckAccess(unittest.TestCase):
    """Tests for BaseStream.check_access() method."""

    def setUp(self):
        self.config = {'start_date': '2024-01-01T00:00:00Z'}
        self.client = MagicMock()

    def test_check_access_returns_true_on_success(self):
        """check_access returns True when the API responds successfully."""
        self.client.make_request.return_value = {"orders": []}
        stream = OrdersStream(self.config, {}, None, self.client)
        self.assertTrue(stream.check_access())

    def test_check_access_returns_false_on_403(self):
        """check_access returns False when EbayForbiddenError is raised."""
        self.client.make_request.side_effect = EbayForbiddenError("Forbidden")
        stream = OrdersStream(self.config, {}, None, self.client)
        self.assertFalse(stream.check_access())

    def test_check_access_propagates_other_errors(self):
        """Non-403 errors are not caught by check_access."""
        self.client.make_request.side_effect = RuntimeError("Server Error")
        stream = OrdersStream(self.config, {}, None, self.client)
        with self.assertRaises(RuntimeError):
            stream.check_access()


class TestDiscoveryAccessExclusion(unittest.TestCase):
    """Tests for stream exclusion during discovery when credentials lack access."""

    def setUp(self):
        self.config = {'start_date': '2024-01-01T00:00:00Z'}

    def _make_runner(self, client):
        args = _make_runner_args(config=self.config)
        return EbayRunner(args, client, AVAILABLE_STREAMS)

    def test_discover_includes_accessible_streams(self):
        """Accessible streams appear in the catalog."""
        client = MagicMock()
        client.make_request.return_value = {"orders": []}
        runner = self._make_runner(client)

        captured = StringIO()
        with patch('sys.stdout', captured):
            runner.do_discover()

        catalog = json.loads(captured.getvalue())
        stream_names = [s['stream'] for s in catalog['streams']]
        self.assertIn('orders', stream_names)

    def test_discover_raises_when_all_streams_forbidden(self):
        """EbayForbiddenError is raised when all streams are inaccessible."""
        client = MagicMock()
        client.make_request.side_effect = EbayForbiddenError("Forbidden")
        runner = self._make_runner(client)

        with self.assertRaises(EbayForbiddenError) as context:
            runner.do_discover()

        self.assertIn("do not have 'read' access to any", str(context.exception))
        self.assertIn("Data collection cannot be initiated", str(context.exception))


if __name__ == '__main__':
    unittest.main()
