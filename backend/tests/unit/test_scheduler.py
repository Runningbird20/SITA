from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.pipeline_job import PipelineJob
from app.scheduler import runner as scheduler_runner


class TestRunScheduler:
    def test_creates_one_job_per_tick(self, monkeypatch):
        engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)
        monkeypatch.setattr(scheduler_runner, "SessionLocal", session_factory)
        monkeypatch.setattr(scheduler_runner, "run_pipeline_job", lambda job_id, since: None)
        monkeypatch.setattr(scheduler_runner.time, "sleep", lambda _seconds: None)

        scheduler_runner.run_scheduler(interval_seconds=0, max_iterations=3)

        with session_factory() as db:
            jobs = db.scalars(select(PipelineJob)).all()
        assert len(jobs) == 3
        engine.dispose()

    def test_first_tick_has_no_since_later_ticks_do(self, monkeypatch):
        engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)
        monkeypatch.setattr(scheduler_runner, "SessionLocal", session_factory)
        monkeypatch.setattr(scheduler_runner, "run_pipeline_job", lambda job_id, since: None)
        monkeypatch.setattr(scheduler_runner.time, "sleep", lambda _seconds: None)

        scheduler_runner.run_scheduler(interval_seconds=0, max_iterations=2)

        with session_factory() as db:
            jobs = db.scalars(select(PipelineJob).order_by(PipelineJob.created_at)).all()
        assert jobs[0].since is None
        assert jobs[1].since is not None
        engine.dispose()
