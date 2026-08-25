import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.models import Base


@pytest.fixture
def db_session():
    """In-memory SQLite session with foreign-key enforcement turned on
    (off by default in SQLite) so FK-integrity tests are meaningful.
    """
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)

    with Session(engine) as session:
        yield session

    engine.dispose()
