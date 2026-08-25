from datetime import datetime

from pydantic import BaseModel


class MitreLoadReport(BaseModel):
    dataset_version: str
    techniques_created: int
    techniques_updated: int


class MitreMappingReport(BaseModel):
    since: datetime | None
    detection_technique_links_created: int
    alerts_processed: int
    alert_technique_mappings_created: int
