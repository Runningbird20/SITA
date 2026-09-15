"""A minimal interval-based scheduler for the full pipeline — resolves
WHATNEXT.md's "Scheduled pipeline runs" item: nothing previously triggered
detection/correlation/triage on a cadence, only a manual POST or CLI call.
See DEF.md § Phase 9, "Post-roadmap addition: scheduled pipeline runs".

Reuses app.jobs.executor.run_pipeline_job() unchanged — a scheduled tick
creates the exact same PipelineJob row a manually-triggered
POST /pipeline/run does, so scheduled and manual runs show up
side-by-side in the same job history, not a separate mechanism.

Deliberately a plain `time.sleep` loop, not a new scheduling dependency
(APScheduler, Celery beat) — one interval, one job type, no cron-style
multi-schedule requirement exists yet. WHATNEXT.md itself named "even just
a documented cron line calling the CLI" as an acceptable answer; this is
a small step past that (tracks `since` incrementally, shows up in the
job/status dashboard) without pulling in real scheduling infrastructure.
"""

import logging
import time
from datetime import UTC, datetime

from app.db.session import SessionLocal
from app.jobs.executor import run_pipeline_job
from app.models.enums import PipelineJobStatus, PipelineJobType
from app.models.pipeline_job import PipelineJob

logger = logging.getLogger(__name__)


def run_scheduler(
    interval_seconds: int = 300,
    max_iterations: int | None = None,
) -> None:
    """`max_iterations` exists for testability (a bounded run); production
    usage (scheduler_cli.py) never passes it, so this runs forever until
    interrupted.

    `since` is tracked incrementally across ticks — the first tick passes
    `since=None` (process all existing history once, matching every other
    pipeline entrypoint's own convention), every tick after that passes
    the previous tick's start time, so a busy system doesn't reprocess its
    entire history every 5 minutes. The already-idempotent pipeline stages
    (fingerprint dedup, force=False triage) mean a wider `since` would
    still be *correct*, just wasteful — this is a performance choice, not
    a correctness one.
    """
    since: datetime | None = None
    iterations = 0

    try:
        while max_iterations is None or iterations < max_iterations:
            iterations += 1
            tick_started_at = datetime.now(UTC)

            db = SessionLocal()
            try:
                job = PipelineJob(
                    job_type=PipelineJobType.PIPELINE_RUN,
                    status=PipelineJobStatus.PENDING,
                    since=since,
                )
                db.add(job)
                db.commit()
                db.refresh(job)
                job_id = job.id
            finally:
                db.close()

            logger.info(
                "scheduled pipeline tick starting",
                extra={"job_id": str(job_id), "since": since.isoformat() if since else None},
            )
            run_pipeline_job(job_id, since)
            since = tick_started_at

            if max_iterations is None or iterations < max_iterations:
                time.sleep(interval_seconds)
    except KeyboardInterrupt:
        pass
