"""Verified identity for every request.

The actor now comes from a signed-in session resolved against the database: the
cookie carries an opaque token and the server holds only its hash. Nothing in the
request body or query can select a user, which is why ``Actor`` has no public
constructor path from client input.

When authentication is not configured (no ``RP_AUTH__SECRET``), resolution keeps
failing with ``AUTH_NOT_CONFIGURED`` instead of silently serving an anonymous
user: a deployment must not appear more open than it is.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from research_platform.core.database import session_dependency
from research_platform.core.errors import DomainError

from . import service

SESSION_COOKIE_FALLBACK = "rp_session"


@dataclass(frozen=True)
class Actor:
    user_id: int


def session_token(request: Request) -> str | None:
    """Read the session cookie using the configured name."""
    for name in _cookie_names(request):
        value = request.cookies.get(name)
        if value:
            return value
    return None


def _cookie_names(request: Request) -> tuple[str, ...]:
    settings = getattr(request.app.state, "settings", None)
    configured = settings.auth.session_cookie if settings and settings.auth else None
    if configured and configured != SESSION_COOKIE_FALLBACK:
        return (configured, SESSION_COOKIE_FALLBACK)
    return (SESSION_COOKIE_FALLBACK,)


def auth_config(request: Request):
    settings = getattr(request.app.state, "settings", None)
    return settings.auth if settings else None


def require_actor(
    request: Request,
    session: Annotated[Session, Depends(session_dependency)],
) -> Actor:
    """Resolve the signed-in user or fail closed."""
    if auth_config(request) is None:
        raise DomainError("AUTH_NOT_CONFIGURED")
    token = session_token(request)
    if not token:
        raise DomainError("AUTHENTICATION_REQUIRED")
    account, _ = service.resolve_session(session, token=token)
    return Actor(user_id=account.id)


def optional_actor(
    request: Request,
    session: Annotated[Session, Depends(session_dependency)],
) -> Actor | None:
    """For read-only public views that render differently when signed in."""
    if auth_config(request) is None:
        return None
    token = session_token(request)
    if not token:
        return None
    try:
        account, _ = service.resolve_session(session, token=token)
    except DomainError:
        return None
    return Actor(user_id=account.id)
