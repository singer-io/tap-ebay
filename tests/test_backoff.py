import unittest
from unittest import mock
from requests.exceptions import ConnectionError
from tap_ebay.client import EbayClient, Server5xxError


AUTH_URL = "https://fake-api.ebay.com/identity/v1/oauth2/token"


class TestEbayClient(unittest.TestCase):
    def setUp(self):
        """
        Set up a mocked EbayClient instance with fake config and patched HTTP requests.
        """
        self.config = {
            'client_id': 'fake_id',
            'client_secret': 'fake_secret',
            'scope': 'https://fake-api.ebay.com/oauth/api_scope',
            'refresh_token': 'fake_token',
            'user_agent': 'test-agent'
        }

        # Patch the authorize() call inside __init__
        patcher = mock.patch('requests.request')
        self.addCleanup(patcher.stop)
        self.mock_request = patcher.start()

        mock_response = mock.Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"token": "fake_access_token"}
        self.mock_request.return_value = mock_response

        self.client = EbayClient(self.config)

    def test_make_request_success(self):
        """
        Test that a successful 200 OK response returns the expected JSON payload.
        """
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "ok"}
        self.mock_request.return_value = mock_response

        result = self.client.make_request("https://fake-api.ebay.com/some-endpoint", "GET")
        self.assertEqual(result, {"result": "ok"})

    def test_make_request_5xx_retries(self):
        """
        Test that 5xx server errors trigger retries and eventually raise Server5xxError.
        """
        error_response = mock.Mock()
        error_response.status_code = 502
        self.mock_request.side_effect = [error_response] * 5

        with self.assertRaises(Server5xxError):
            self.client.make_request("https://fake-api.ebay.com/some-endpoint", "GET")

        self.assertEqual(self.mock_request.call_count, 6)

    def test_make_request_non_200_raises_runtime_error(self):
        """
        Test that non-200 non-5xx responses raise a RuntimeError with error message.
        """
        error_response = mock.Mock()
        error_response.status_code = 403
        error_response.text = "Forbidden"
        self.mock_request.return_value = error_response

        with self.assertRaises(RuntimeError) as context:
            self.client.make_request("https://fake-api.ebay.com/some-endpoint", "GET")
        self.assertIn("Forbidden", str(context.exception))

    def test_make_request_with_params_and_body(self):
        """
        Test that query parameters and JSON body are correctly passed to the request.
        """
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "ok"}
        self.mock_request.return_value = mock_response

        result = self.client.make_request(
            "https://fake-api.ebay.com/some-endpoint",
            "POST",
            params={"q": "item"},
            body={"key": "value"}
        )
        self.assertEqual(result, {"result": "ok"})

        _, kwargs = self.mock_request.call_args
        self.assertEqual(kwargs["params"], {"q": "item"})
        self.assertEqual(kwargs["json"], {"key": "value"})

    def test_make_request_connection_error_retries(self):
        """
        Test that ConnectionError triggers retries and is eventually raised.
        """
        self.mock_request.side_effect = ConnectionError("Temporary network issue")

        with self.assertRaises(ConnectionError):
            self.client.make_request("https://fake-api.ebay.com/some-endpoint", "GET")

        self.assertEqual(self.mock_request.call_count, 6)

    def test_authorize_sets_access_token(self):
        """
        Test that the authorize method sets the access token from the response.
        """
        # Re-patch just for this isolated test
        with mock.patch("requests.request") as mock_req:
            mock_response = mock.Mock()
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = {"access_token": "mock_token"}
            mock_req.return_value = mock_response

            client = EbayClient(self.config)
            self.assertEqual(client.access_token, "mock_token")
