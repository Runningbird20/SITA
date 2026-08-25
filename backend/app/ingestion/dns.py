from app.ingestion.base import IngestionAdapter, IngestionValidationError, require_enum, require_str
from app.models.enums import SourceType

_QUERY_TYPES = {"A", "AAAA", "CNAME", "TXT", "MX", "NS"}
_RESPONSE_CODES = {"NOERROR", "NXDOMAIN", "SERVFAIL", "REFUSED"}


class DNSIngestionAdapter(IngestionAdapter):
    source_type = SourceType.DNS

    def normalize(self, raw: dict) -> dict:
        normalized = {
            "query_name": require_str(raw, "query_name"),
            "query_type": require_enum(raw, "query_type", _QUERY_TYPES),
            "response_code": require_enum(raw, "response_code", _RESPONSE_CODES),
            "resolver_ip": require_str(raw, "resolver_ip"),
        }
        resolved_ips = raw.get("resolved_ips")
        if resolved_ips is not None:
            if not isinstance(resolved_ips, list) or not all(
                isinstance(ip, str) for ip in resolved_ips
            ):
                raise IngestionValidationError(
                    "field must be a list of strings: resolved_ips", field="resolved_ips"
                )
            normalized["resolved_ips"] = resolved_ips
        return normalized
