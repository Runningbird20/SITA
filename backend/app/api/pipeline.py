from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, require_admin
from app.core.audit import record_audit
from app.core.config import get_settings
from app.correlation.pipeline import run_correlation
from app.db.session import get_db
from app.detection.pipeline import run_detection
from app.ioc.pipeline import run_ioc_extraction
from app.mitre.pipeline import run_mitre_mapping
from app.schemas.pipeline_run import PipelineRunReport, PipelineRunRequest
from app.schemas.triage_run import TriageReanalyzeRequest, TriageRunReport
from app.triage.pipeline import run_triage

router = APIRouter(prefix=f"{get_settings().api_v1_prefix}/pipeline", tags=["pipeline"])


@router.post("/run", response_model=PipelineRunReport)
def run_pipeline(
    request: PipelineRunRequest = PipelineRunRequest(),
    db: Session = Depends(get_db),
    current_user: CurrentUser | None = Depends(require_admin),
) -> PipelineRunReport:
    """Run the full deterministic-then-AI pipeline — detection, IOC
    extraction, MITRE mapping, correlation, triage — against whatever
    SecurityEvents already exist. For demo purposes; does not ingest.
    See DEF.md § Phase 9. Admin-only (post-roadmap, Phase 14) — see
    DEF.md § Phase 14, "Multi-user / RBAC".
    """
    since = request.since

    detection_report = run_detection(db, since=since)
    ioc_report = run_ioc_extraction(db, since=since)
    mitre_report = run_mitre_mapping(db, since=since)
    correlation_report = run_correlation(db, since=since)
    triage_report = run_triage(db, since=since)
    record_audit(db, current_user, action="pipeline.run", detail={"since": str(since)})
    db.commit()

    return PipelineRunReport(
        since=since,
        detection=detection_report,
        ioc=ioc_report,
        mitre=mitre_report,
        correlation=correlation_report,
        triage=triage_report,
    )


@router.post("/reanalyze", response_model=TriageRunReport)
def reanalyze(
    request: TriageReanalyzeRequest = TriageReanalyzeRequest(),
    db: Session = Depends(get_db),
    current_user: CurrentUser | None = Depends(require_admin),
) -> TriageRunReport:
    """Re-run just the AI triage step, `force=True` — regenerates every
    task for every matching incident even if a valid `AnalysisResult`
    already exists, unlike `POST /pipeline/run`'s triage pass (which
    skips anything already done). For picking up a prompt/model change
    without re-running the (already-idempotent) deterministic stages.
    Admin-only, same as `/pipeline/run` — see DEF.md § Phase 14,
    "Multi-user / RBAC".
    """
    since = request.since
    triage_report = run_triage(db, since=since, force=True)
    record_audit(db, current_user, action="triage.reanalyze", detail={"since": str(since)})
    db.commit()
    return triage_report
