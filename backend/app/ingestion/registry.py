from app.ingestion.auth import AuthIngestionAdapter
from app.ingestion.base import IngestionAdapter
from app.ingestion.dns import DNSIngestionAdapter
from app.ingestion.endpoint import EndpointIngestionAdapter
from app.ingestion.network import NetworkIngestionAdapter
from app.ingestion.web import WebIngestionAdapter
from app.models.enums import SourceType

_ADAPTERS: dict[SourceType, IngestionAdapter] = {
    SourceType.AUTH: AuthIngestionAdapter(),
    SourceType.ENDPOINT: EndpointIngestionAdapter(),
    SourceType.NETWORK: NetworkIngestionAdapter(),
    SourceType.DNS: DNSIngestionAdapter(),
    SourceType.WEB: WebIngestionAdapter(),
}


def get_adapter(source_type: SourceType) -> IngestionAdapter:
    return _ADAPTERS[source_type]
