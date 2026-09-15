import threading
import time

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.ingestion.file_tail import tail_file
from app.models import Base
from app.models.event import SecurityEvent


def _make_session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine), engine


class TestTailFile:
    def test_ingests_a_line_appended_after_startup(self, tmp_path):
        # The line must land *after* tail_file has already seeked to EOF,
        # not before — otherwise this collapses into the
        # from-existing-content case below. A background thread appends
        # it mid-poll while the main thread's tail_file loop is running.
        log_path = tmp_path / "auth.log"
        log_path.write_text("")
        session_factory, engine = _make_session_factory()

        def _append_soon():
            time.sleep(0.2)
            with log_path.open("a") as handle:
                handle.write(
                    "Jan 15 03:00:00 db01 sshd[1234]: Failed password for admin "
                    "from 198.51.100.1 port 22 ssh2\n"
                )

        writer = threading.Thread(target=_append_soon)
        writer.start()
        # 20 iterations * 0.05s poll = ~1s of polling window, comfortably
        # past the writer thread's 0.2s delay. The trailing flush in
        # tail_file's own `finally` block ingests whatever's buffered once
        # max_iterations is reached, regardless of flush_interval_seconds.
        tail_file(
            log_path,
            poll_interval_seconds=0.05,
            db_factory=session_factory,
            max_iterations=20,
        )
        writer.join()

        with session_factory() as db:
            events = db.scalars(select(SecurityEvent)).all()
        assert len(events) == 1
        assert events[0].normalized["username"] == "admin"
        engine.dispose()

    def test_does_not_ingest_pre_existing_content_by_default(self, tmp_path):
        log_path = tmp_path / "auth.log"
        log_path.write_text(
            "Jan 15 03:00:00 db01 sshd[1234]: Failed password for admin "
            "from 198.51.100.1 port 22 ssh2\n"
        )
        session_factory, engine = _make_session_factory()

        tail_file(
            log_path,
            poll_interval_seconds=0,
            db_factory=session_factory,
            max_iterations=3,
        )

        with session_factory() as db:
            events = db.scalars(select(SecurityEvent)).all()
        assert events == []
        engine.dispose()

    def test_from_start_ingests_pre_existing_content(self, tmp_path):
        log_path = tmp_path / "auth.log"
        log_path.write_text(
            "Jan 15 03:00:00 db01 sshd[1234]: Failed password for admin "
            "from 198.51.100.1 port 22 ssh2\n"
        )
        session_factory, engine = _make_session_factory()

        tail_file(
            log_path,
            poll_interval_seconds=0,
            db_factory=session_factory,
            max_iterations=3,
            from_start=True,
        )

        with session_factory() as db:
            events = db.scalars(select(SecurityEvent)).all()
        assert len(events) == 1
        engine.dispose()

    def test_unrecognized_lines_are_skipped_not_ingested(self, tmp_path):
        log_path = tmp_path / "auth.log"
        log_path.write_text("")
        session_factory, engine = _make_session_factory()

        with log_path.open("a") as handle:
            handle.write("Jan 15 03:00:00 db01 cron[99]: some unrelated cron message\n")

        tail_file(
            log_path,
            poll_interval_seconds=0,
            db_factory=session_factory,
            max_iterations=3,
        )

        with session_factory() as db:
            events = db.scalars(select(SecurityEvent)).all()
        assert events == []
        engine.dispose()
