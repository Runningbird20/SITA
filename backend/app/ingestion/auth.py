from app.ingestion.base import IngestionAdapter, require_enum, require_str
from app.models.enums import SourceType

_EVENT_RESULTS = {"success", "failure"}
_AUTH_METHODS = {"password", "publickey", "mfa"}


class AuthIngestionAdapter(IngestionAdapter):
    source_type = SourceType.AUTH

    def normalize(self, raw: dict) -> dict:
        return {
            "event_result": require_enum(raw, "event_result", _EVENT_RESULTS),
            "username": require_str(raw, "username"),
            "source_ip": require_str(raw, "source_ip"),
            "dest_host": raw["host"],
            "auth_method": require_enum(raw, "auth_method", _AUTH_METHODS),
        }
