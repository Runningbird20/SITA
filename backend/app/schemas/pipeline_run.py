from datetime import datetime

from pydantic import BaseModel

from app.schemas.correlation_run import CorrelationRunReport
from app.schemas.detection_run import DetectionRunReport
from app.schemas.ioc_run import IOCExtractionReport
from app.schemas.mitre_run import MitreMappingReport
from app.schemas.triage_run import TriageRunReport


class PipelineRunRequest(BaseModel):
    since: datetime | None = None


class PipelineRunReport(BaseModel):
    since: datetime | None
    detection: DetectionRunReport
    ioc: IOCExtractionReport
    mitre: MitreMappingReport
    correlation: CorrelationRunReport
    triage: TriageRunReport
