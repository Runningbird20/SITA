from datetime import datetime

from pydantic import BaseModel


class TriageReanalyzeRequest(BaseModel):
    since: datetime | None = None


class TriageRunReport(BaseModel):
    since: datetime | None
    incidents_processed: int
    analysis_results_created: int
    analysis_results_skipped: int
    recommendations_created: int
    mitre_mappings_created: int
    by_task_type: dict[str, int]
