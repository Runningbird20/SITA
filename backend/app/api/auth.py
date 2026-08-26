from fastapi import APIRouter, Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, get_current_user, require_admin
from app.auth.service import authenticate, create_user, issue_token, revoke_token
from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import LoginRequest, LoginResponse, UserCreate, UserRead

router = APIRouter(prefix=f"{get_settings().api_v1_prefix}/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    """No rate limiting beyond the general per-IP tier already applied to
    every /api/v1/* route (app/core/rate_limit.py) — a dedicated
    brute-force throttle for this specific endpoint is real, useful
    hardening this MVP deliberately doesn't include yet (see WHATNEXT.md).
    """
    user = authenticate(db, body.username, body.password)
    if user is None:
        raise UnauthorizedError("Invalid username or password")
    raw_token, token_row = issue_token(db, user, get_settings().auth_token_expiry_days)
    db.commit()
    return LoginResponse(
        token=raw_token, user=UserRead.model_validate(user), expires_at=token_row.expires_at
    )


@router.post("/logout", status_code=204)
def logout(
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
    _current_user: CurrentUser | None = Depends(get_current_user),
) -> None:
    """A no-op (still 204), not an error, if there was no session to
    revoke — same "clearing something absent isn't a failure" convention
    as DELETE /analysis-results/{id}/feedback.
    """
    if authorization and authorization.startswith("Bearer "):
        revoke_token(db, authorization.removeprefix("Bearer "))
        db.commit()


@router.get("/me", response_model=UserRead | None)
def me(
    current_user: CurrentUser | None = Depends(get_current_user), db: Session = Depends(get_db)
) -> User | None:
    """None when auth is disabled — lets the frontend distinguish "no
    login required" from "logged in as X" with one call.
    """
    if current_user is None:
        return None
    return db.get(User, current_user.id)


@router.post("/users", response_model=UserRead, status_code=201)
def create_new_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    _admin: CurrentUser | None = Depends(require_admin),
) -> User:
    """Admin-only. The very first user can't be created this way (there's
    no admin yet to authorize it) — see `app/auth/cli.py`'s bootstrap
    command.
    """
    user = create_user(db, body.username, body.password, body.role)
    db.commit()
    db.refresh(user)
    return user


@router.get("/users", response_model=list[UserRead])
def list_users(
    db: Session = Depends(get_db), _admin: CurrentUser | None = Depends(require_admin)
) -> list[User]:
    return list(db.scalars(select(User).order_by(User.username)).all())
