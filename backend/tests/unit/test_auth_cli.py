from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.auth import cli
from app.models import Base
from app.models.enums import UserRole
from app.models.user import User


def _wire_test_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    test_session_local = sessionmaker(bind=engine)
    monkeypatch.setattr(cli, "SessionLocal", test_session_local)
    return test_session_local


class TestAuthCli:
    def test_create_user_with_password_argument(self, monkeypatch, capsys):
        session_local = _wire_test_db(monkeypatch)

        exit_code = cli.main(["create-user", "admin1", "a-real-password", "--role", "admin"])
        assert exit_code == 0
        assert "admin1" in capsys.readouterr().out

        with session_local() as db:
            user = db.scalars(select(User).where(User.username == "admin1")).one()
            assert user.role == UserRole.ADMIN
            assert user.password_hash != "a-real-password"

    def test_default_role_is_analyst(self, monkeypatch):
        session_local = _wire_test_db(monkeypatch)

        cli.main(["create-user", "analyst1", "a-real-password"])

        with session_local() as db:
            user = db.scalars(select(User).where(User.username == "analyst1")).one()
            assert user.role == UserRole.ANALYST

    def test_password_prompted_when_omitted(self, monkeypatch):
        session_local = _wire_test_db(monkeypatch)
        monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: "prompted-password")

        cli.main(["create-user", "admin2", "--role", "admin"])

        with session_local() as db:
            user = db.scalars(select(User).where(User.username == "admin2")).one()
            assert user.password_hash  # hashed, present — real assertion is it didn't crash
