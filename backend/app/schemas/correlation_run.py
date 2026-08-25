from datetime import datetime

from pydantic import BaseModel


class CorrelationRunReport(BaseModel):
    since: datetime | None
    alerts_processed: int
    incidents_created: int
    incidents_joined: int
    host_entities_created: int
    host_links_created: int
