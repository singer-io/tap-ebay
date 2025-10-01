from tap_ebay.streams.base import BaseStream
import singer
from singer import metadata as meta

LOGGER = singer.get_logger()  # noqa


class OrdersStream(BaseStream):
    API_METHOD = 'GET'
    TABLE = 'orders'
    KEY_PROPERTIES = ['orderId']

    # Keep the class consistent with the catalog we emit
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

    # Minimal, stream-level change
    def generate_catalog(self):
        entries = super().generate_catalog()   # base returns a 1-item list for this stream
        entry = entries[0]

        # Convert metadata to a map
        m = meta.to_map(entry["metadata"])
        root = m.get((), {})
        root["inclusion"] = root.get("inclusion", "available")
        root["replication-method"] = "FULL_TABLE"
        root["forced-replication-method"] = "FULL_TABLE"
        root["valid-replication-keys"] = []
        m[()] = root

        entry["metadata"] = meta.to_list(m)
        return entries
