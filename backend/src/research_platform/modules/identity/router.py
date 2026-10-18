"""Authentication HTTP surface.

The cookie is the only credential the browser holds; the token itself never
appears in a response body or a log. ``HttpOnly`` keeps it away from JavaScript,
``SameSite=Lax`` blocks cross-site form posts while allowing normal navigation,
and ``Secure`` is required in production (enforced at startup).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from research_platform.core.database import session_dependency
from research_platform.core.errors import DomainError

from . import service
from .dependencies import Actor, auth_config, optional_actor, require_actor, session_token
from .schemas import ChangePasswordRequest, LoginRequest, RegisterRequest, SessionRead, UserRead

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

SessionDep = Annotated[Session, Depends(session_dependency)]


def _user_read(account) -> UserRead:
    from datetime import UTC

    def aware(value):
        return None if value is None else value.replace(tzinfo=UTC)

    return UserRead(
        id=account.id,
        email=account.email,
        display_name=account.display_name,
        role=account.role,
        is_active=account.is_active,
        created_at=aware(account.created_at),
        last_signed_in_at=aware(account.last_signed_in_at),
    )


def _set_session_cookie(request: Request, response: Response, token: str) -> None:
    config = auth_config(request)
    if config is None:
        raise DomainError("AUTH_NOT_CONFIGURED")
    response.set_cookie(
        key=config.session_cookie,
        value=token,
        max_age=int(config.session_ttl_hours * 3600),
        httponly=True,
        secure=config.cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post(
    "/register", response_model=SessionRead, status_code=201, operation_id="register_account"
)
def register(data: RegisterRequest, request: Request, response: Response, session: SessionDep):
    """Create an account and sign in immediately."""
    account = service.register(
        session,
        auth_config(request),
        email=str(data.email),
        password=data.password,
        display_name=data.display_name,
    )
    account, token, expires_at = service.login(
        session,
        auth_config(request),
        email=str(data.email),
        password=data.password,
        user_agent=request.headers.get("user-agent", ""),
        client_address=request.client.host if request.client else "",
    )
    _set_session_cookie(request, response, token)
    return SessionRead(user=_user_read(account), expires_at=expires_at)


@router.post("/login", response_model=SessionRead, operation_id="login")
def login(data: LoginRequest, request: Request, response: Response, session: SessionDep):
    """Sign in and set the session cookie."""
    account, token, expires_at = service.login(
        session,
        auth_config(request),
        email=str(data.email),
        password=data.password,
        user_agent=request.headers.get("user-agent", ""),
        client_address=request.client.host if request.client else "",
    )
    _set_session_cookie(request, response, token)
    return SessionRead(user=_user_read(account), expires_at=expires_at)


@router.post("/logout", status_code=204, operation_id="logout")
def logout(request: Request, response: Response, session: SessionDep):
    """Revoke the current session server-side and clear the cookie."""
    token = session_token(request)
    if token:
        service.logout(session, token=token)
    config = auth_config(request)
    response.delete_cookie(config.session_cookie if config else "rp_session", path="/")
    return Response(status_code=204)


@router.get("/session", response_model=SessionRead | None, operation_id="get_current_session")
def current_session(
    request: Request,
    actor: Annotated[Actor | None, Depends(optional_actor)],
    session: SessionDep,
):
    """Who is signed in, or ``null``. Never fails on a missing cookie."""
    if actor is None:
        return None
    account, row = service.resolve_session(session, token=session_token(request) or "")
    return SessionRead(user=_user_read(account), expires_at=row.expires_at)


@router.post("/password", status_code=204, operation_id="change_password")
def change_password(
    data: ChangePasswordRequest,
    request: Request,
    response: Response,
    actor: Annotated[Actor, Depends(require_actor)],
    session: SessionDep,
):
    """Change the password and revoke every other session."""
    service.change_password(
        session,
        auth_config(request),
        user_id=actor.user_id,
        current_password=data.current_password,
        new_password=data.new_password,
    )
    config = auth_config(request)
    response.delete_cookie(config.session_cookie if config else "rp_session", path="/")
    return Response(status_code=204)
