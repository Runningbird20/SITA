from datetime import datetime

from pydantic import BaseModel


class IOCExtractionReport(BaseModel):
    since: datetime | None
    events_scanned: int
    iocs_created: int
    iocs_updated: int
    event_links_created: int
    alert_links_created: int
    iocs_by_type: dict[str, int]
