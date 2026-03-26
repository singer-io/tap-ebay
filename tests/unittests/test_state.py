"""
Unit tests for tap_ebay.state and tap_ebay.config — bookmark management and config parsing.
"""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from tap_ebay.state import (
    get_last_record_value_for_table,
    incorporate,
    load_state,
    save_state,
)


# ---------------------------------------------------------------------------
# get_last_record_value_for_table()
# ---------------------------------------------------------------------------

class TestGetLastRecordValue(unittest.TestCase):
    """Tests for get_last_record_value_for_table()."""

    def test_returns_none_for_empty_state(self):
        """Returns None when state is an empty dict."""
        self.assertIsNone(get_last_record_value_for_table({}, 'orders'))

    def test_returns_none_when_bookmarks_key_is_absent(self):
        """Returns None when 'bookmarks' key does not exist in state."""
        self.assertIsNone(get_last_record_value_for_table({'other': {}}, 'orders'))

    def test_returns_none_when_table_not_in_bookmarks(self):
        """Returns None when the requested table has no bookmark."""
        state = {'bookmarks': {'other_table': {'last_record': '2024-01-01T00:00:00Z'}}}
        self.assertIsNone(get_last_record_value_for_table(state, 'orders'))

    def test_returns_none_when_last_record_is_absent(self):
        """Returns None when the table bookmark exists but has no 'last_record'."""
        state = {'bookmarks': {'orders': {'field': 'creationDate'}}}
        self.assertIsNone(get_last_record_value_for_table(state, 'orders'))

    def test_returns_parsed_datetime_for_valid_bookmark(self):
        """Returns a parsed datetime object matching the stored bookmark value."""
        from dateutil.parser import parse
        state = {'bookmarks': {'orders': {'last_record': '2024-03-15T10:00:00Z'}}}
        result = get_last_record_value_for_table(state, 'orders')
        self.assertEqual(result, parse('2024-03-15T10:00:00Z'))

    def test_returns_none_for_null_last_record(self):
        """Returns None when last_record is explicitly None."""
        state = {'bookmarks': {'orders': {'last_record': None}}}
        self.assertIsNone(get_last_record_value_for_table(state, 'orders'))


# ---------------------------------------------------------------------------
# incorporate()
# ---------------------------------------------------------------------------

class TestIncorporate(unittest.TestCase):
    """Tests for incorporate() — bookmark update logic."""

    def test_returns_original_state_unchanged_when_value_is_none(self):
        """Passing value=None returns the state without modification."""
        state = {'bookmarks': {'orders': {'last_record': '2024-01-01T00:00:00Z'}}}
        result = incorporate(state, 'orders', 'lastModifiedDate', None)
        self.assertEqual(result, state)

    def test_creates_bookmarks_key_when_absent(self):
        """Creates 'bookmarks' top-level key if missing from state."""
        result = incorporate({}, 'orders', 'lastModifiedDate', '2024-01-15T00:00:00Z')
        self.assertIn('bookmarks', result)

    def test_creates_table_bookmark_when_absent(self):
        """Creates table entry under bookmarks when none existed."""
        result = incorporate({}, 'orders', 'lastModifiedDate', '2024-01-15T00:00:00Z')
        self.assertIn('orders', result['bookmarks'])

    def test_stores_field_name_in_bookmark(self):
        """Bookmark entry includes the field name used for incremental replication."""
        result = incorporate({}, 'orders', 'lastModifiedDate', '2024-01-15T00:00:00Z')
        self.assertEqual(result['bookmarks']['orders']['field'], 'lastModifiedDate')

    def test_stores_parsed_timestamp_in_bookmark(self):
        """last_record value is stored in normalised ISO 8601 UTC format."""
        result = incorporate({}, 'orders', 'lastModifiedDate', '2024-01-15T10:30:00Z')
        last_record = result['bookmarks']['orders']['last_record']
        self.assertRegex(last_record, r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z')

    def test_updates_bookmark_when_new_value_is_later(self):
        """Bookmark is updated when the new value is more recent than the stored one."""
        state = {'bookmarks': {'orders': {'last_record': '2024-01-01T00:00:00Z', 'field': 'f'}}}
        result = incorporate(state, 'orders', 'f', '2024-06-01T00:00:00Z')
        self.assertGreater(
            result['bookmarks']['orders']['last_record'],
            '2024-01-01T00:00:00Z'
        )

    def test_does_not_update_bookmark_when_new_value_is_older(self):
        """Bookmark is NOT updated when the new value is earlier than the stored one."""
        state = {
            'bookmarks': {'orders': {'last_record': '2024-06-01T00:00:00Z', 'field': 'f'}}
        }
        result = incorporate(state, 'orders', 'f', '2024-01-01T00:00:00Z')
        self.assertEqual(result['bookmarks']['orders']['last_record'], '2024-06-01T00:00:00Z')

    def test_does_not_mutate_original_state_dict(self):
        """incorporate() returns a new state dict and does not alter the original."""
        original = {}
        incorporate(original, 'orders', 'f', '2024-01-01T00:00:00Z')
        self.assertEqual(original, {})

    def test_does_not_update_for_equal_value(self):
        """Bookmark is NOT updated when the new value equals the stored one."""
        state = {'bookmarks': {'orders': {'last_record': '2024-01-01T00:00:00Z', 'field': 'f'}}}
        result = incorporate(state, 'orders', 'f', '2024-01-01T00:00:00Z')
        # same value — last_record should remain unchanged
        self.assertEqual(result['bookmarks']['orders']['last_record'], '2024-01-01T00:00:00Z')


# ---------------------------------------------------------------------------
# save_state()
# ---------------------------------------------------------------------------

class TestSaveState(unittest.TestCase):
    """Tests for save_state() — Singer STATE message output."""

    @patch('tap_ebay.state.singer.write_state')
    def test_save_state_calls_write_state_with_state(self, mock_write):
        """save_state() delegates to singer.write_state() with the full state dict."""
        state = {'bookmarks': {'orders': {}}}
        save_state(state)
        mock_write.assert_called_once_with(state)

    @patch('tap_ebay.state.singer.write_state')
    def test_save_state_does_nothing_for_empty_dict(self, mock_write):
        """save_state({}) calls singer.write_state (falsy dict is still truthy for empty dict)."""
        # {} is falsy in a boolean context — state module checks `if not state`
        save_state({})
        mock_write.assert_not_called()

    @patch('tap_ebay.state.singer.write_state')
    def test_save_state_does_nothing_for_none(self, mock_write):
        """save_state(None) is a no-op."""
        save_state(None)
        mock_write.assert_not_called()

    @patch('tap_ebay.state.singer.write_state')
    def test_save_state_non_empty_state_is_written(self, mock_write):
        """save_state() writes state when the dict has contents."""
        state = {'bookmarks': {'orders': {'last_record': '2024-01-01T00:00:00Z'}}}
        save_state(state)
        mock_write.assert_called_once()


# ---------------------------------------------------------------------------
# load_state()
# ---------------------------------------------------------------------------

class TestLoadState(unittest.TestCase):
    """Tests for load_state() — reading state from disk."""

    def test_returns_empty_dict_for_none_filename(self):
        """load_state(None) returns an empty dict without touching the filesystem."""
        result = load_state(None)
        self.assertEqual(result, {})

    def test_loads_valid_json_file(self):
        """load_state() correctly parses a valid JSON state file."""
        state_data = {
            'bookmarks': {'orders': {'last_record': '2024-01-01T00:00:00Z', 'field': 'f'}}
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as fh:
            json.dump(state_data, fh)
            fname = fh.name
        try:
            result = load_state(fname)
            self.assertEqual(result, state_data)
        finally:
            os.unlink(fname)

    def test_raises_runtime_error_for_invalid_json(self):
        """load_state() raises RuntimeError when the file contains invalid JSON."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as fh:
            fh.write('not valid json {{{')
            fname = fh.name
        try:
            with self.assertRaises(RuntimeError):
                load_state(fname)
        finally:
            os.unlink(fname)

    def test_loads_empty_object_json(self):
        """load_state() handles a file containing just '{}'."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as fh:
            json.dump({}, fh)
            fname = fh.name
        try:
            result = load_state(fname)
            self.assertEqual(result, {})
        finally:
            os.unlink(fname)


# ---------------------------------------------------------------------------
# get_config_start_date()
# ---------------------------------------------------------------------------

class TestGetConfigStartDate(unittest.TestCase):
    """Tests for tap_ebay.config.get_config_start_date()."""

    def test_returns_parsed_start_date(self):
        """get_config_start_date() parses the start_date string into a datetime."""
        from dateutil.parser import parse
        from tap_ebay.config import get_config_start_date
        config = {'start_date': '2024-01-15T00:00:00Z'}
        result = get_config_start_date(config)
        self.assertEqual(result, parse('2024-01-15T00:00:00Z'))

    def test_returns_datetime_object(self):
        """get_config_start_date() returns a datetime instance."""
        from datetime import datetime
        from tap_ebay.config import get_config_start_date
        config = {'start_date': '2024-06-01T12:30:00Z'}
        result = get_config_start_date(config)
        self.assertIsInstance(result, datetime)

    def test_handles_date_only_start_date(self):
        """get_config_start_date() handles a date-only string (no time component)."""
        from tap_ebay.config import get_config_start_date
        config = {'start_date': '2024-01-01'}
        result = get_config_start_date(config)
        self.assertEqual(result.year, 2024)
        self.assertEqual(result.month, 1)
        self.assertEqual(result.day, 1)


if __name__ == '__main__':
    unittest.main()
