from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.correlation.pipeline import run_correlation
from app.db.session import get_db
from app.detection.pipeline import run_detection
from app.ioc.pipeline import run_ioc_extraction
from app.mitre.pipeline import run_mitre_mapping
from app.schemas.pipeline_run import PipelineRunReport, PipelineRunRequest
from app.triage.pipeline import run_triage

router = APIRouter(prefix=f"{get_settings().api_v1_prefix}/pipeline", tags=["pipeline"])


@router.post("/run", response_model=PipelineRunReport)
def run_pipeline(
    request: PipelineRunRequest = PipelineRunRequest(),
    db: Session = Depends(get_db),
) -> PipelineRunReport:
    """Run the full deterministic-then-AI pipeline — detection, IOC
    extraction, MITRE mapping, correlation, triage — against whatever
    SecurityEvents already exist. For demo purposes; does not ingest.
    See DEF.md § Phase 9.
    """
    since = request.since

    detection_report = run_detection(db, since=since)
    ioc_report = run_ioc_extraction(db, since=since)
    mitre_report = run_mitre_mapping(db, since=since)
    correlation_report = run_correlation(db, since=since)
    triage_report = run_triage(db, since=since)
    db.commit()

    return PipelineRunReport(
        since=since,
        detection=detection_report,
        ioc=ioc_report,
        mitre=mitre_report,
        correlation=correlation_report,
        triage=triage_report,
    )
