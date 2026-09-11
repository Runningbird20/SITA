import uuid

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, get_current_user, require_admin
from app.core.audit import record_audit
from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.jobs.executor import run_pipeline_job, run_reanalyze_job
from app.models.enums import PipelineJobStatus, PipelineJobType
from app.models.pipeline_job import PipelineJob
from app.schemas.pipeline_job import PipelineJobRead
from app.schemas.pipeline_run import PipelineRunRequest
from app.schemas.triage_run import TriageReanalyzeRequest

router = APIRouter(prefix=f"{get_settings().api_v1_prefix}/pipeline", tags=["pipeline"])


@router.post("/run", response_model=PipelineJobRead, status_code=202)
def run_pipeline(
    background_tasks: BackgroundTasks,
    request: PipelineRunRequest = PipelineRunRequest(),
    db: Session = Depends(get_db),
    current_user: CurrentUser | None = Depends(require_admin),
) -> PipelineJobRead:
    """Schedules the full deterministic-then-AI pipeline — detection, IOC
    extraction, MITRE mapping, correlation, triage — against whatever
    SecurityEvents already exist, and returns immediately with a job to
    poll rather than blocking for the run's full duration (Phase 15
    measured ~5.5 minutes for a 10-incident, 60-call real Ollama run).
    Poll `GET /pipeline/jobs/{id}` for status/progress and the final
    report. For demo purposes; does not ingest. See DEF.md § Phase 9,
    "Post-roadmap addition: background pipeline jobs". Admin-only
    (post-roadmap, Phase 14) — see DEF.md § Phase 14, "Multi-user / RBAC".
    """
    since = request.since
    job = PipelineJob(
        job_type=PipelineJobType.PIPELINE_RUN,
        status=PipelineJobStatus.PENDING,
        since=since,
        created_by_id=current_user.id if current_user else None,
    )
    db.add(job)
    db.flush()
    record_audit(
        db, current_user, action="pipeline.run", detail={"since": str(since), "job_id": str(job.id)}
    )
    db.commit()
    db.refresh(job)

    background_tasks.add_task(run_pipeline_job, job.id, since)
    return PipelineJobRead.model_validate(job)


@router.post("/reanalyze", response_model=PipelineJobRead, status_code=202)
def reanalyze(
    background_tasks: BackgroundTasks,
    request: TriageReanalyzeRequest = TriageReanalyzeRequest(),
    db: Session = Depends(get_db),
    current_user: CurrentUser | None = Depends(require_admin),
) -> PipelineJobRead:
    """Schedules just the AI triage step, `force=True` — regenerates every
    task for every matching incident even if a valid `AnalysisResult`
    already exists, unlike `POST /pipeline/run`'s triage pass (which
    skips anything already done). For picking up a prompt/model change
    without re-running the (already-idempotent) deterministic stages.
    Returns immediately with a job to poll, same as `/pipeline/run` — see
    DEF.md § Phase 9, "Post-roadmap addition: background pipeline jobs".
    Admin-only, same as `/pipeline/run` — see DEF.md § Phase 14,
    "Multi-user / RBAC".
    """
    since = request.since
    job = PipelineJob(
        job_type=PipelineJobType.TRIAGE_REANALYZE,
        status=PipelineJobStatus.PENDING,
        since=since,
        created_by_id=current_user.id if current_user else None,
    )
    db.add(job)
    db.flush()
    record_audit(
        db,
        current_user,
        action="triage.reanalyze",
        detail={"since": str(since), "job_id": str(job.id)},
    )
    db.commit()
    db.refresh(job)

    background_tasks.add_task(run_reanalyze_job, job.id, since)
    return PipelineJobRead.model_validate(job)


@router.get("/jobs/{job_id}", response_model=PipelineJobRead)
def get_pipeline_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser | None = Depends(get_current_user),
) -> PipelineJobRead:
    """Read-only status poll — any authenticated user (or anyone, if auth
    is disabled) can check a job's progress, not just admins; triggering
    one is the privileged action, watching it finish isn't.
    """
    job = db.get(PipelineJob, job_id)
    if job is None:
        raise NotFoundError("PipelineJob", job_id)
    return PipelineJobRead.model_validate(job)
