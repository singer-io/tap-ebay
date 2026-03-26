"""
Unit tests for tap_ebay sync — EbayRunner orchestration, stream sync, and record output.
"""
import unittest
from unittest.mock import MagicMock, patch, call

from singer import metadata as meta

from tap_ebay import EbayRunner
from tap_ebay.streams import AVAILABLE_STREAMS
from tap_ebay.streams.base import BaseStream
from tap_ebay.streams.orders import OrdersStream


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_catalog_entry(stream_name, selected=True, inclusion='available'):
    """Build a mock catalog stream entry with selection metadata."""
    mdata = meta.new()
    mdata = meta.write(mdata, (), 'inclusion', inclusion)
    if selected is not None:
        mdata = meta.write(mdata, (), 'selected', selected)
    entry = MagicMock()
    entry.stream = stream_name
    entry.tap_stream_id = stream_name
    entry.metadata = meta.to_list(mdata)
    return entry


def _make_args(config=None, state=None, catalog_streams=None):
    args = MagicMock()
    args.config = config or {'start_date': '2024-01-01T00:00:00Z'}
    args.state = state or {}
    catalog = MagicMock()
    catalog.streams = catalog_streams or []
    args.catalog = catalog
    return args


def _make_orders_stream(records=None):
    """Construct an OrdersStream with mocked catalog and client."""
    config = {'start_date': '2024-01-01T00:00:00Z'}
    catalog = MagicMock()
    catalog.stream = 'orders'
    catalog.tap_stream_id = 'orders'
    catalog.metadata = None
    catalog.schema.to_dict.return_value = {
        'type': 'object',
        'properties': {
            'orderId': {'type': 'string'},
            'creationDate': {'type': ['string', 'null']},
        }
    }
    catalog.key_properties = ['orderId']
    client = MagicMock()
    client.make_request.return_value = {'orders': records if records is not None else [{'orderId': 'order-1'}]}
    return OrdersStream(config, {}, catalog, client)


# ---------------------------------------------------------------------------
# EbayRunner.get_streams_to_replicate()
# ---------------------------------------------------------------------------

class TestGetStreamsToReplicate(unittest.TestCase):
    """Tests for EbayRunner.get_streams_to_replicate() stream selection logic."""

    def test_selected_stream_is_included(self):
        """A selected orders stream is returned by get_streams_to_replicate()."""
        args = _make_args(catalog_streams=[_make_catalog_entry('orders', selected=True)])
        runner = EbayRunner(args, MagicMock(), AVAILABLE_STREAMS)
        streams = runner.get_streams_to_replicate()
        self.assertEqual(len(streams), 1)
        self.assertIsInstance(streams[0], OrdersStream)

    def test_unselected_stream_is_excluded(self):
        """A stream with selected=False is excluded from replication."""
        args = _make_args(catalog_streams=[_make_catalog_entry('orders', selected=False)])
        runner = EbayRunner(args, MagicMock(), AVAILABLE_STREAMS)
        streams = runner.get_streams_to_replicate()
        self.assertEqual(len(streams), 0)

    def test_unknown_stream_name_in_catalog_is_ignored(self):
        """A catalog entry whose name doesn't match any available stream is skipped."""
        args = _make_args(catalog_streams=[_make_catalog_entry('invoices', selected=True)])
        runner = EbayRunner(args, MagicMock(), AVAILABLE_STREAMS)
        streams = runner.get_streams_to_replicate()
        self.assertEqual(len(streams), 0)

    def test_empty_catalog_returns_empty_list(self):
        """No catalog streams means no streams to replicate."""
        args = _make_args(catalog_streams=[])
        runner = EbayRunner(args, MagicMock(), AVAILABLE_STREAMS)
        streams = runner.get_streams_to_replicate()
        self.assertEqual(streams, [])

    def test_stream_with_unmet_requirements_raises_runtime_error(self):
        """RuntimeError is raised when required sub-streams are not selected."""
        mock_cls = MagicMock()
        mock_cls.TABLE = 'orders'
        mock_cls.REQUIRES = ['missing_stream']
        mock_cls.matches_catalog.return_value = True
        mock_cls.requirements_met.return_value = False

        args = _make_args(catalog_streams=[_make_catalog_entry('orders', selected=True)])
        runner = EbayRunner(args, MagicMock(), [mock_cls])
        with self.assertRaises(RuntimeError):
            runner.get_streams_to_replicate()

    def test_automatic_inclusion_selects_stream(self):
        """inclusion=automatic without explicit selected flag includes the stream."""
        args = _make_args(
            catalog_streams=[_make_catalog_entry('orders', selected=None, inclusion='automatic')]
        )
        runner = EbayRunner(args, MagicMock(), AVAILABLE_STREAMS)
        streams = runner.get_streams_to_replicate()
        self.assertEqual(len(streams), 1)


# ---------------------------------------------------------------------------
# EbayRunner.do_sync()
# ---------------------------------------------------------------------------

class TestDoSync(unittest.TestCase):
    """Tests for EbayRunner.do_sync() orchestration."""

    def _runner_with_mock_streams(self, stream_list, state=None):
        args = _make_args(state=state or {})
        runner = EbayRunner(args, MagicMock(), AVAILABLE_STREAMS)
        runner.get_streams_to_replicate = MagicMock(return_value=stream_list)
        return runner

    @patch('tap_ebay.save_state')
    def test_do_sync_calls_sync_for_each_stream(self, mock_save):
        """do_sync() calls stream.sync() for every stream returned by get_streams_to_replicate."""
        mock_stream = MagicMock()
        mock_stream.state = {}
        runner = self._runner_with_mock_streams([mock_stream])
        runner.do_sync()
        mock_stream.sync.assert_called_once()

    @patch('tap_ebay.save_state')
    def test_do_sync_calls_save_state_at_end(self, mock_save):
        """do_sync() calls save_state() after all streams have synced."""
        runner = self._runner_with_mock_streams([])
        runner.do_sync()
        mock_save.assert_called_once()

    @patch('tap_ebay.save_state')
    def test_do_sync_sets_stream_state_from_runner(self, mock_save):
        """do_sync() passes runner.state into each stream before calling sync."""
        initial_state = {'bookmarks': {'orders': {'last_record': '2024-01-01T00:00:00Z'}}}
        mock_stream = MagicMock()
        mock_stream.state = initial_state
        runner = self._runner_with_mock_streams([mock_stream], state=initial_state)
        runner.do_sync()
        self.assertEqual(mock_stream.state, initial_state)

    @patch('tap_ebay.save_state')
    def test_do_sync_re_raises_generic_exception(self, mock_save):
        """do_sync() re-raises non-OS exceptions from stream.sync()."""
        mock_stream = MagicMock()
        mock_stream.state = {}
        mock_stream.TABLE = 'orders'
        mock_stream.sync.side_effect = ValueError('unexpected error')
        runner = self._runner_with_mock_streams([mock_stream])
        with self.assertRaises(ValueError):
            runner.do_sync()

    @patch('tap_ebay.save_state')
    def test_do_sync_multiple_streams_all_synced(self, mock_save):
        """do_sync() calls sync() on every stream in the list."""
        mock_streams = [MagicMock(state={}) for _ in range(3)]
        runner = self._runner_with_mock_streams(mock_streams)
        runner.do_sync()
        for s in mock_streams:
            s.sync.assert_called_once()


# ---------------------------------------------------------------------------
# OrdersStream.get_stream_data()
# ---------------------------------------------------------------------------

class TestOrdersStreamGetStreamData(unittest.TestCase):
    """Tests for OrdersStream.get_stream_data() — eBay response extraction."""

    def setUp(self):
        self.stream = _make_orders_stream()

    def test_get_stream_data_returns_list(self):
        """get_stream_data() always returns a list."""
        with patch.object(self.stream, 'transform_record', side_effect=lambda r: r):
            result = self.stream.get_stream_data({'orders': [{'orderId': 'o1'}]})
        self.assertIsInstance(result, list)

    def test_get_stream_data_extracts_all_records(self):
        """get_stream_data() returns one element per order in the response."""
        with patch.object(self.stream, 'transform_record', side_effect=lambda r: r):
            result = self.stream.get_stream_data(
                {'orders': [{'orderId': 'o1'}, {'orderId': 'o2'}]}
            )
        self.assertEqual(len(result), 2)

    def test_get_stream_data_returns_empty_list_for_zero_orders(self):
        """get_stream_data() returns [] when orders list is empty."""
        with patch.object(self.stream, 'transform_record', side_effect=lambda r: r):
            result = self.stream.get_stream_data({'orders': []})
        self.assertEqual(result, [])

    def test_get_stream_data_applies_transform_record(self):
        """get_stream_data() applies transform_record to each order."""
        transformed = {'orderId': 'transformed'}
        with patch.object(self.stream, 'transform_record', return_value=transformed):
            result = self.stream.get_stream_data({'orders': [{'orderId': 'raw'}]})
        self.assertEqual(result, [transformed])

    def test_get_stream_data_preserves_order_of_records(self):
        """get_stream_data() preserves the order of records from the API response."""
        orders = [{'orderId': 'a'}, {'orderId': 'b'}, {'orderId': 'c'}]
        with patch.object(self.stream, 'transform_record', side_effect=lambda r: r):
            result = self.stream.get_stream_data({'orders': orders})
        self.assertEqual([r['orderId'] for r in result], ['a', 'b', 'c'])


# ---------------------------------------------------------------------------
# Base.sync() and Base.sync_data()
# ---------------------------------------------------------------------------

class TestBaseSyncData(unittest.TestCase):
    """Tests for Base.sync() and Base.sync_data() — Singer protocol output."""

    @patch('singer.metrics.record_counter')
    @patch('singer.write_records')
    @patch('singer.write_schema')
    def test_sync_calls_write_schema(self, mock_write_schema, mock_write_records, mock_counter):
        """sync() calls singer.write_schema() exactly once before syncing data."""
        stream = _make_orders_stream()
        with patch.object(stream, 'transform_record', side_effect=lambda r: r):
            stream.sync()
        mock_write_schema.assert_called_once()

    @patch('singer.metrics.record_counter')
    @patch('singer.write_records')
    @patch('singer.write_schema')
    def test_sync_data_calls_make_request(self, mock_write_schema, mock_write_records, mock_counter):
        """sync_data() calls client.make_request with the stream URL and method."""
        stream = _make_orders_stream()
        with patch.object(stream, 'transform_record', side_effect=lambda r: r):
            stream.sync_data()
        stream.client.make_request.assert_called_once_with(stream.get_url(), 'GET')

    @patch('singer.metrics.record_counter')
    @patch('singer.write_records')
    @patch('singer.write_schema')
    def test_sync_data_writes_one_record_per_order(self, mock_ws, mock_wr, mock_counter):
        """sync_data() calls singer.write_records() once per order returned."""
        stream = _make_orders_stream(records=[{'orderId': 'r1'}, {'orderId': 'r2'}])
        with patch.object(stream, 'transform_record', side_effect=lambda r: r):
            stream.sync_data()
        self.assertEqual(mock_wr.call_count, 2)

    @patch('singer.metrics.record_counter')
    @patch('singer.write_records')
    @patch('singer.write_schema')
    def test_sync_data_writes_records_to_correct_table(self, mock_ws, mock_wr, mock_counter):
        """singer.write_records() is called with the 'orders' table name."""
        stream = _make_orders_stream(records=[{'orderId': 'r1'}])
        with patch.object(stream, 'transform_record', side_effect=lambda r: r):
            stream.sync_data()
        call_args = mock_wr.call_args
        self.assertEqual(call_args[0][0], 'orders')

    @patch('singer.metrics.record_counter')
    @patch('singer.write_records')
    @patch('singer.write_schema')
    def test_sync_data_zero_orders_writes_no_records(self, mock_ws, mock_wr, mock_counter):
        """sync_data() writes no records when API returns an empty orders list."""
        stream = _make_orders_stream(records=[])
        with patch.object(stream, 'transform_record', side_effect=lambda r: r):
            stream.sync_data()
        mock_wr.assert_not_called()


# ---------------------------------------------------------------------------
# BaseStream filter / param helpers
# ---------------------------------------------------------------------------

class TestBaseStreamFilterAndParams(unittest.TestCase):
    """Tests for BaseStream.get_filter(), get_params(), and get_url()."""

    def setUp(self):
        self.stream = OrdersStream({'start_date': '2024-01-01T00:00:00Z'}, {}, None, None)

    def test_get_filter_contains_last_modified_date_field(self):
        """get_filter() produces a filter string referencing 'lastmodifieddate'."""
        from datetime import datetime
        result = self.stream.get_filter(datetime(2024, 1, 1))
        self.assertIn('lastmodifieddate', result)

    def test_get_filter_contains_formatted_start_date(self):
        """get_filter() includes the date formatted as ISO 8601 with milliseconds."""
        from datetime import datetime
        result = self.stream.get_filter(datetime(2024, 3, 1, 12, 0, 0))
        self.assertIn('2024-03-01T12:00:00.000Z', result)

    def test_get_params_contains_filter_key(self):
        """get_params() returns dict with 'filter' key."""
        from datetime import datetime
        params = self.stream.get_params(datetime(2024, 1, 1), 0, 200)
        self.assertIn('filter', params)

    def test_get_params_contains_limit(self):
        """get_params() returns the specified limit value."""
        from datetime import datetime
        params = self.stream.get_params(datetime(2024, 1, 1), 0, 100)
        self.assertEqual(params['limit'], 100)

    def test_get_params_contains_offset(self):
        """get_params() returns the specified offset value."""
        from datetime import datetime
        params = self.stream.get_params(datetime(2024, 1, 1), 50, 200)
        self.assertEqual(params['offset'], 50)

    def test_get_url_combines_base_and_path(self):
        """get_url() returns the production eBay API base URL joined with the stream path."""
        expected = 'https://api.ebay.com/sell/fulfillment/v1/order'
        self.assertEqual(self.stream.get_url(), expected)

    def test_get_url_uses_sandbox_base_when_sandbox_true(self):
        """get_url() returns the sandbox eBay API base URL when config sandbox=True."""
        sandbox_stream = OrdersStream(
            {'start_date': '2024-01-01T00:00:00Z', 'sandbox': True}, {}, None, None
        )
        self.assertIn('sandbox.ebay.com', sandbox_stream.get_url())

    def test_get_url_uses_prod_base_when_sandbox_false(self):
        """get_url() returns the production eBay API base URL when config sandbox=False."""
        prod_stream = OrdersStream(
            {'start_date': '2024-01-01T00:00:00Z', 'sandbox': False}, {}, None, None
        )
        self.assertNotIn('sandbox', prod_stream.get_url())

    def test_get_url_defaults_to_prod_when_sandbox_not_in_config(self):
        """get_url() defaults to production when 'sandbox' key is absent from config."""
        stream = OrdersStream(
            {'start_date': '2024-01-01T00:00:00Z'}, {}, None, None
        )
        self.assertNotIn('sandbox', stream.get_url())


if __name__ == '__main__':
    unittest.main()
