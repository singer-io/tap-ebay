from tap_ebay.streams.base import BaseStream
import singer

LOGGER = singer.get_logger()  # noqa


class OrdersStream(BaseStream):
    API_METHOD = 'GET'
    TABLE = 'orders'
    KEY_PROPERTIES = ['orderId']

    REPLICATION_METHOD = "FULL_TABLE"
    REPLICATION_KEYS = []
    FORCED_REPLICATION_METHOD = "FULL_TABLE"

    @property
    def path(self):
        return '/sell/fulfillment/v1/order'

    def get_stream_data(self, result):
        return [
            self.transform_record(record)
            for record in result['orders']
        ]
