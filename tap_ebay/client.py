import backoff
import base64
import requests
import requests.auth
from requests.exceptions import ConnectionError
import singer
import singer.metrics
import time



DEFAULT_RETRY_RATE_LIMIT = 360

LOGGER = singer.get_logger()  # noqa

AUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"



class Server5xxError(Exception):
    pass


class Server429Error(Exception):
    pass


class EbayClient:

    def __init__(self, config):
        self.config = config
        self._retry_after = DEFAULT_RETRY_RATE_LIMIT
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


    def _rate_limit_backoff(self):
        """
        Bound wait‐generator: on each retry backoff will call next()
        and sleep for self._retry_after seconds.
        """
        while True:
            yield self._retry_after

    def make_request(self, AUTH_URL, method, params=None, body=None):
        @backoff.on_exception(
            self._rate_limit_backoff,
            Server429Error,
            max_tries=5,
            jitter=None,
        )
        @backoff.on_exception(
            backoff.expo,
            (ConnectionError, Server5xxError),
            max_tries=5,
        )
        def _call():
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
            elif resp.status_code == 429:
                try:
                    self._retry_after = int(
                        float(resp.headers.get("X-EBAY-C-RATE-LIMIT", DEFAULT_RETRY_RATE_LIMIT))
                    )
                except (TypeError, ValueError):
                    self._retry_after = DEFAULT_RETRY_RATE_LIMIT
                raise Server429Error()
            elif resp.status_code != 200:
                raise RuntimeError(resp.text)

            return resp

        response = _call()
        return response.json()
