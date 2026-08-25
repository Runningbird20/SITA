from app.ingestion.base import (
    IngestionAdapter,
    optional_int,
    optional_str,
    require_int,
    require_str,
)
from app.models.enums import SourceType


class EndpointIngestionAdapter(IngestionAdapter):
    source_type = SourceType.ENDPOINT

    def normalize(self, raw: dict) -> dict:
        normalized = {
            "process_name": require_str(raw, "process_name"),
            "command_line": require_str(raw, "command_line"),
            "pid": require_int(raw, "pid"),
            "user": require_str(raw, "user"),
        }
        parent_pid = optional_int(raw, "parent_pid")
        if parent_pid is not None:
            normalized["parent_pid"] = parent_pid
        parent_process_name = optional_str(raw, "parent_process_name")
        if parent_process_name is not None:
            normalized["parent_process_name"] = parent_process_name
        return normalized
