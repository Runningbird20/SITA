"""Background execution for the pipeline-trigger endpoints — resolves
WHATNEXT.md's "Background job execution for triage" item. See DEF.md §
Phase 9, "Post-roadmap addition: background pipeline jobs".

Runs via FastAPI's BackgroundTasks, after the triggering request has
already returned a PipelineJobRead with status="pending" — so each
function here opens its own DB session rather than reusing the request's
(which is closed by the time this code runs). Every write commits
immediately after the field it sets, so a concurrent GET /pipeline/jobs/{id}
from a different request (possibly a different worker process, under
docker-compose.prod.yml's multi-worker backend) sees up-to-date progress,
not a batch of changes held until the very end.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.correlation.pipeline import run_correlation
from app.db.session import SessionLocal
from app.detection.pipeline import run_detection
from app.ioc.pipeline import run_ioc_extraction
from app.mitre.pipeline import run_mitre_mapping
from app.models.enums import PipelineJobStatus, PipelineStage
from app.models.pipeline_job import PipelineJob
from app.notifications.registry import get_notifier
from app.schemas.pipeline_run import PipelineRunReport
from app.triage.pipeline import run_triage

logger = logging.getLogger(__name__)


def _mark_running(db: Session, job: PipelineJob) -> None:
    job.status = PipelineJobStatus.RUNNING
    job.started_at = datetime.now(UTC)
    db.commit()


def _mark_failed(db: Session, job_id: uuid.UUID, exc: Exception) -> None:
    db.rollback()
    job = db.get(PipelineJob, job_id)
    if job is None:
        return
    job.status = PipelineJobStatus.FAILED
    job.error = str(exc)
    job.completed_at = datetime.now(UTC)
    db.commit()
    logger.exception("pipeline job failed", extra={"job_id": str(job_id)})


def run_pipeline_job(job_id: uuid.UUID, since: datetime | None) -> None:
    db = SessionLocal()
    try:
        job = db.get(PipelineJob, job_id)
        if job is None:
            return
        _mark_running(db, job)

        def set_stage(stage: PipelineStage) -> None:
            job.current_stage = stage
            db.commit()

        def set_progress(current: int, total: int) -> None:
            job.progress_current = current
            job.progress_total = total
            db.commit()

        set_stage(PipelineStage.DETECTION)
        detection_report = run_detection(db, since=since)
        db.commit()

        set_stage(PipelineStage.IOC)
        ioc_report = run_ioc_extraction(db, since=since)
        db.commit()

        set_stage(PipelineStage.MITRE)
        mitre_report = run_mitre_mapping(db, since=since)
        db.commit()

        set_stage(PipelineStage.CORRELATION)
        correlation_report = run_correlation(db, since=since, notifier=get_notifier())
        db.commit()

        set_stage(PipelineStage.TRIAGE)
        triage_report = run_triage(db, since=since, on_progress=set_progress)
        db.commit()

        report = PipelineRunReport(
            since=since,
            detection=detection_report,
            ioc=ioc_report,
            mitre=mitre_report,
            correlation=correlation_report,
            triage=triage_report,
        )
        job.status = PipelineJobStatus.COMPLETED
        job.result = report.model_dump(mode="json")
        job.completed_at = datetime.now(UTC)
        db.commit()
    except Exception as exc:  # a job's own failure must never propagate to BackgroundTasks
        _mark_failed(db, job_id, exc)
    finally:
        db.close()


def run_reanalyze_job(job_id: uuid.UUID, since: datetime | None) -> None:
    db = SessionLocal()
    try:
        job = db.get(PipelineJob, job_id)
        if job is None:
            return
        _mark_running(db, job)
        job.current_stage = PipelineStage.TRIAGE
        db.commit()

        def set_progress(current: int, total: int) -> None:
            job.progress_current = current
            job.progress_total = total
            db.commit()

        triage_report = run_triage(db, since=since, force=True, on_progress=set_progress)
        db.commit()

        job.status = PipelineJobStatus.COMPLETED
        job.result = triage_report.model_dump(mode="json")
        job.completed_at = datetime.now(UTC)
        db.commit()
    except Exception as exc:  # a job's own failure must never propagate to BackgroundTasks
        _mark_failed(db, job_id, exc)
    finally:
        db.close()
