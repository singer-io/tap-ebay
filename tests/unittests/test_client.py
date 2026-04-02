"""
Unit tests for tap_ebay.client — EbayClient HTTP authentication and request logic.
"""
import base64
import unittest
from unittest.mock import MagicMock, patch

import requests

from tap_ebay.client import EbayClient, Server5xxError


CONFIG = {
    'client_id': 'test_id',
    'client_secret': 'test_secret',
    'scope': 'https://api.ebay.com/oauth/api_scope',
    'refresh_token': 'test_refresh_token',
    'user_agent': 'test-agent/1.0',
}


def _make_auth_response(token='test_access_token'):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {'access_token': token}
    return resp


class TestEbayClientAuthorize(unittest.TestCase):
    """Tests for EbayClient.authorize() — OAuth token acquisition."""

    @patch('tap_ebay.client.requests.request')
    def test_authorize_returns_access_token(self, mock_req):
        """authorize() stores the access_token from the OAuth response."""
        mock_req.return_value = _make_auth_response('my_token')
        client = EbayClient(CONFIG)
        self.assertEqual(client.access_token, 'my_token')

    @patch('tap_ebay.client.requests.request')
    def test_authorize_sends_basic_auth_header(self, mock_req):
        """authorize() encodes client_id:client_secret as Basic auth."""
        mock_req.return_value = _make_auth_response()
        EbayClient(CONFIG)
        _, kwargs = mock_req.call_args
        expected = 'Basic ' + base64.b64encode(b'test_id:test_secret').decode()
        self.assertEqual(kwargs['headers']['Authorization'], expected)

    @patch('tap_ebay.client.requests.request')
    def test_authorize_sends_grant_type_refresh_token(self, mock_req):
        """authorize() sends grant_type=refresh_token in form data."""
        mock_req.return_value = _make_auth_response()
        EbayClient(CONFIG)
        _, kwargs = mock_req.call_args
        self.assertEqual(kwargs['data']['grant_type'], 'refresh_token')

    @patch('tap_ebay.client.requests.request')
    def test_authorize_sends_scope_from_config(self, mock_req):
        """authorize() sends the scope value from config."""
        mock_req.return_value = _make_auth_response()
        EbayClient(CONFIG)
        _, kwargs = mock_req.call_args
        self.assertEqual(kwargs['data']['scope'], CONFIG['scope'])

    @patch('tap_ebay.client.requests.request')
    def test_authorize_sends_refresh_token_from_config(self, mock_req):
        """authorize() sends the refresh_token value from config."""
        mock_req.return_value = _make_auth_response()
        EbayClient(CONFIG)
        _, kwargs = mock_req.call_args
        self.assertEqual(kwargs['data']['refresh_token'], CONFIG['refresh_token'])

    @patch('tap_ebay.client.requests.request')
    def test_authorize_posts_to_oauth_token_url(self, mock_req):
        """authorize() makes a POST request to the eBay OAuth token endpoint."""
        mock_req.return_value = _make_auth_response()
        EbayClient(CONFIG)
        args, _ = mock_req.call_args
        self.assertEqual(args[0], 'POST')
        self.assertIn('oauth2/token', args[1])

    @patch('tap_ebay.client.requests.request')
    def test_authorize_raises_on_http_error(self, mock_req):
        """authorize() raises HTTPError when the token request fails."""
        resp = MagicMock()
        resp.raise_for_status.side_effect = requests.HTTPError('401 Unauthorized')
        mock_req.return_value = resp
        with self.assertRaises(requests.HTTPError):
            EbayClient(CONFIG)

    @patch('tap_ebay.client.requests.request')
    def test_authorize_sends_content_type_form_urlencoded(self, mock_req):
        """authorize() sets Content-Type to application/x-www-form-urlencoded."""
        mock_req.return_value = _make_auth_response()
        EbayClient(CONFIG)
        _, kwargs = mock_req.call_args
        self.assertEqual(kwargs['headers']['Content-Type'], 'application/x-www-form-urlencoded')

    @patch('tap_ebay.client.requests.request')
    def test_authorize_uses_prod_url_by_default(self, mock_req):
        """authorize() POSTs to the production OAuth URL when sandbox not in config."""
        mock_req.return_value = _make_auth_response()
        EbayClient(CONFIG)
        args, _ = mock_req.call_args
        self.assertIn('api.ebay.com', args[1])
        self.assertNotIn('sandbox', args[1])

    @patch('tap_ebay.client.requests.request')
    def test_authorize_uses_prod_url_when_sandbox_false(self, mock_req):
        """authorize() POSTs to the production OAuth URL when sandbox=False."""
        mock_req.return_value = _make_auth_response()
        EbayClient({**CONFIG, 'sandbox': False})
        args, _ = mock_req.call_args
        self.assertNotIn('sandbox', args[1])

    @patch('tap_ebay.client.requests.request')
    def test_authorize_uses_sandbox_url_when_sandbox_true(self, mock_req):
        """authorize() POSTs to the sandbox OAuth URL when sandbox=True."""
        mock_req.return_value = _make_auth_response()
        EbayClient({**CONFIG, 'sandbox': True})
        args, _ = mock_req.call_args
        self.assertIn('sandbox.ebay.com', args[1])


class TestEbayClientMakeRequest(unittest.TestCase):
    """Tests for EbayClient.make_request() — HTTP dispatch and error mapping."""

    def setUp(self):
        with patch('tap_ebay.client.requests.request') as mock_req:
            mock_req.return_value = _make_auth_response('bearer_token')
            self.client = EbayClient(CONFIG)

    @patch('tap_ebay.client.requests.request')
    def test_make_request_success_returns_json(self, mock_req):
        """Successful 200 response returns parsed JSON body."""
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {'orders': []}
        mock_req.return_value = resp
        result = self.client.make_request('https://api.ebay.com/order', 'GET')
        self.assertEqual(result, {'orders': []})

    @patch('tap_ebay.client.requests.request')
    def test_make_request_sends_bearer_authorization_header(self, mock_req):
        """make_request() includes Authorization: Bearer <token> header."""
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {}
        mock_req.return_value = resp
        self.client.make_request('https://api.ebay.com/order', 'GET')
        _, kwargs = mock_req.call_args
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer bearer_token')

    @patch('tap_ebay.client.requests.request')
    def test_make_request_500_raises_server5xx_error(self, mock_req):
        """500 response raises Server5xxError."""
        resp = MagicMock()
        resp.status_code = 500
        mock_req.return_value = resp
        with self.assertRaises(Server5xxError):
            self.client.make_request('https://api.ebay.com/order', 'GET')

    @patch('tap_ebay.client.requests.request')
    def test_make_request_502_raises_server5xx_error(self, mock_req):
        """502 Bad Gateway raises Server5xxError."""
        resp = MagicMock()
        resp.status_code = 502
        mock_req.return_value = resp
        with self.assertRaises(Server5xxError):
            self.client.make_request('https://api.ebay.com/order', 'GET')

    @patch('tap_ebay.client.requests.request')
    def test_make_request_404_raises_runtime_error_with_message(self, mock_req):
        """Non-200 non-5xx response raises RuntimeError containing response text."""
        resp = MagicMock()
        resp.status_code = 404
        resp.text = 'Not Found'
        mock_req.return_value = resp
        with self.assertRaises(RuntimeError) as ctx:
            self.client.make_request('https://api.ebay.com/order', 'GET')
        self.assertIn('Not Found', str(ctx.exception))

    @patch('tap_ebay.client.requests.request')
    def test_make_request_401_raises_runtime_error(self, mock_req):
        """401 Unauthorized raises RuntimeError."""
        resp = MagicMock()
        resp.status_code = 401
        resp.text = 'Unauthorized'
        mock_req.return_value = resp
        with self.assertRaises(RuntimeError):
            self.client.make_request('https://api.ebay.com/order', 'GET')

    @patch('tap_ebay.client.requests.request')
    def test_make_request_passes_query_params(self, mock_req):
        """Query params dict is forwarded to the HTTP request."""
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {}
        mock_req.return_value = resp
        self.client.make_request('https://api.ebay.com/order', 'GET', params={'limit': 50})
        _, kwargs = mock_req.call_args
        self.assertEqual(kwargs['params'], {'limit': 50})

    @patch('tap_ebay.client.requests.request')
    def test_make_request_passes_json_body(self, mock_req):
        """JSON body dict is forwarded as json= kwarg to the HTTP request."""
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {}
        mock_req.return_value = resp
        self.client.make_request('https://api.ebay.com/order', 'POST', body={'key': 'val'})
        _, kwargs = mock_req.call_args
        self.assertEqual(kwargs['json'], {'key': 'val'})

    @patch('tap_ebay.client.requests.request')
    def test_make_request_sends_content_type_json(self, mock_req):
        """make_request() sets Content-Type: application/json header."""
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {}
        mock_req.return_value = resp
        self.client.make_request('https://api.ebay.com/order', 'GET')
        _, kwargs = mock_req.call_args
        self.assertEqual(kwargs['headers']['Content-Type'], 'application/json')


if __name__ == '__main__':
    unittest.main()
