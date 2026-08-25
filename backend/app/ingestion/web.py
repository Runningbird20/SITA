from app.ingestion.base import (
    IngestionAdapter,
    optional_str,
    require_enum,
    require_int,
    require_str,
)
from app.models.enums import SourceType

_METHODS = {"GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"}


class WebIngestionAdapter(IngestionAdapter):
    source_type = SourceType.WEB

    def normalize(self, raw: dict) -> dict:
        normalized = {
            "method": require_enum(raw, "method", _METHODS),
            "path": require_str(raw, "path"),
            "status_code": require_int(raw, "status_code"),
            "source_ip": require_str(raw, "source_ip"),
            "host": raw["host"],
        }
        user_agent = optional_str(raw, "user_agent")
        if user_agent is not None:
            normalized["user_agent"] = user_agent
        return normalized
