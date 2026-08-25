from app.ingestion.base import (
    IngestionAdapter,
    optional_int,
    require_enum,
    require_int,
    require_str,
)
from app.models.enums import SourceType

_PROTOCOLS = {"tcp", "udp", "icmp"}


class NetworkIngestionAdapter(IngestionAdapter):
    source_type = SourceType.NETWORK

    def normalize(self, raw: dict) -> dict:
        normalized = {
            "src_ip": require_str(raw, "src_ip"),
            "src_port": require_int(raw, "src_port"),
            "dst_ip": require_str(raw, "dst_ip"),
            "dst_port": require_int(raw, "dst_port"),
            "protocol": require_enum(raw, "protocol", _PROTOCOLS),
        }
        bytes_sent = optional_int(raw, "bytes_sent")
        if bytes_sent is not None:
            normalized["bytes_sent"] = bytes_sent
        bytes_received = optional_int(raw, "bytes_received")
        if bytes_received is not None:
            normalized["bytes_received"] = bytes_received
        return normalized
