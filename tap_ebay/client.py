import backoff
import base64
import requests
from requests.exceptions import ConnectionError
import singer


LOGGER = singer.get_logger()  # noqa

PROD_AUTH_URL    = "https://api.ebay.com/identity/v1/oauth2/token"
SANDBOX_AUTH_URL = "https://api.sandbox.ebay.com/identity/v1/oauth2/token"

PROD_API_BASE    = 'https://api.ebay.com'
SANDBOX_API_BASE = 'https://api.sandbox.ebay.com'


class Server5xxError(Exception):
    pass


class EbayClient:

    def __init__(self, config):
        self.config = config
        self.access_token = self.authorize()

    def authorize(self):
        is_sandbox = self.config.get('sandbox', False)
        auth_url = SANDBOX_AUTH_URL if is_sandbox else PROD_AUTH_URL

        client = "{}:{}".format(self.config.get('client_id'),
                                self.config.get('client_secret'))
        auth = base64.b64encode(client.encode()).decode()

        data = {
            "grant_type": "refresh_token",
            "scope": self.config.get('scope'),
            "refresh_token": self.config.get('refresh_token')
        }

        headers = {
            'Content-Type': "application/x-www-form-urlencoded",
            'Authorization': "Basic {}".format(auth),
            'User-Agent': self.config.get('user_agent')
        }

        response = requests.request("POST",
                                    auth_url,
                                    data=data,
                                    headers=headers)

        response.raise_for_status()
        data = response.json()

        return data['access_token']


    # The below Implementation does not have the Retry logic since the Ebay Orders API
    # Endpoint have 24 hours Quota of 100,000 calls , Retry is not supported
    # Reference - https://developer.ebay.com/develop/get-started/api-call-limits
    @backoff.on_exception(
        backoff.expo,
        (ConnectionError, Server5xxError),
        max_tries=5,
    )
    def make_request(self, url, method, params=None, body=None):

        LOGGER.info("Making {} request to {}".format(method, url))

        resp = requests.request(
            method,
            url,
            headers={
                'Authorization': "Bearer {}".format(self.access_token),
                'Content-Type': 'application/json',
                'User-Agent': self.config.get('user_agent')
            },
            params=params,
            json=body,
        )
        if 500 <= resp.status_code < 600:
            raise Server5xxError()
        elif resp.status_code != 200:
            raise RuntimeError(resp.text)
        return resp.json()
