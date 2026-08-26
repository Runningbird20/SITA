from datetime import datetime

from pydantic import BaseModel


class DetectionRunReport(BaseModel):
    since: datetime | None
    rules_run: int
    alerts_created: int
    alerts_by_rule: dict[str, int]
    duplicates_skipped: int = 0
