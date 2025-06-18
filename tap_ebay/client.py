import backoff
import base64
import requests
import requests.auth
from requests.exceptions import ConnectionError
import singer
import singer.metrics
import time


LOGGER = singer.get_logger()  # noqa

AUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"


class Server5xxError(Exception):
    pass


class EbayClient:

    def __init__(self, config):
        self.config = config
        self.access_token = self.authorize()

    def authorize(self):
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
                                    AUTH_URL,
                                    data=data,
                                    headers=headers)

        response.raise_for_status()
        data = response.json()

        self.token = data['access_token']

    def refresh_access_token(self):
        LOGGER.info("Refreshing access token")
        data = {'grant_type': 'refresh_token', 'refresh_token': self.config['refresh_token']}
        response = requests.request("POST", AUTH_URL, data=data)
        return response.json()['access_token']


    # The below implementation does not have the Retry logic since the Ebay Orders API
    # endpoint have 24 hours Quota of 100,000 calls , Retry is not supported
    # Reference - https://developer.ebay.com/develop/get-started/api-call-limits
    @backoff.on_exception(
        backoff.expo,
        (ConnectionError, Server5xxError),
        max_tries=5,
    )
    def make_request(self, AUTH_URL, method, params=None, body=None):

        LOGGER.info("Making {} request to {}".format(method, AUTH_URL))

        resp = requests.request(
            method,
            AUTH_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer {}".format(self.access_token),
            },
            params=params,
            json=body,
        )
        if resp.status_code >= 500 and resp.status_code < 600:
            raise Server5xxError()
        elif resp.status_code != 200:
            raise RuntimeError(resp.text)
        return resp.json()
