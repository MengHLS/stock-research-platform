"""Invitation codes: issue, list, revoke and consume.

A code is the approval for one account. Only its hash is stored, so the plaintext
exists exactly once — in the operator's terminal when it is created. Consumption is
a conditional UPDATE, so two concurrent registrations cannot both spend the same
code.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from research_platform.core.config import AuthConfig
from research_platform.core.errors import DomainError

from .models import InvitationCode, utc_now
from .security import hash_session_token

# 10 URL-safe bytes ≈ 80 bits of entropy: unguessable, and short enough to paste.
CODE_BYTES = 10
CODE_PREFIX = "rp_"


def new_code() -> str:
    return f"{CODE_PREFIX}{secrets.token_urlsafe(CODE_BYTES)}"


def _hash(code: str) -> str:
    return hash_session_token(code.strip())


def issue(
    session: Session,
    config: AuthConfig | None,
    *,
    label: str = "",
    ttl_hours: int | None = None,
) -> tuple[str, InvitationCode]:
    """Create a code and return ``(plaintext, row)`` — the plaintext is not stored."""
    if config is None:
        raise DomainError("AUTH_NOT_CONFIGURED")
    hours = ttl_hours if ttl_hours is not None else config.invitation_ttl_hours
    code = new_code()
    row = InvitationCode(
        id=str(uuid.uuid4()),
        code_hash=_hash(code),
        label=label.strip()[:120],
        expires_at=utc_now() + timedelta(hours=hours) if hours > 0 else None,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return code, row


def consume(session: Session, code: str) -> InvitationCode:
    """Validate and spend a code; raises when it cannot be used.

    The update is conditional on the row still being unused, unrevoked and
    unexpired, so the check and the spend are one atomic statement.
    """
    now = utc_now()
    row = session.scalar(select(InvitationCode).where(InvitationCode.code_hash == _hash(code)))
    if row is None:
        # One code for "unknown" and "already used" would be friendlier to
        # attackers; the operator-facing distinction is kept in the audit instead.
        raise DomainError("INVITATION_CODE_INVALID")
    if row.revoked_at is not None:
        raise DomainError("INVITATION_CODE_INVALID")
    if row.used_at is not None:
        raise DomainError("INVITATION_CODE_ALREADY_USED")
    if row.expires_at is not None and row.expires_at <= now:
        raise DomainError("INVITATION_CODE_EXPIRED")

    changed = session.execute(
        update(InvitationCode)
        .where(
            InvitationCode.id == row.id,
            InvitationCode.used_at.is_(None),
            InvitationCode.revoked_at.is_(None),
        )
        .values(used_at=now)
    )
    if changed.rowcount != 1:
        # Another registration spent it between the read and the update.
        raise DomainError("INVITATION_CODE_ALREADY_USED")
    session.commit()
    session.refresh(row)
    return row


def attach_user(session: Session, invitation: InvitationCode, user_id: int) -> None:
    """Record which account the code produced (best effort, same transaction)."""
    invitation.used_by_user_id = user_id
    session.add(invitation)
    session.commit()


def list_codes(session: Session, *, limit: int = 50) -> list[InvitationCode]:
    return list(
        session.scalars(
            select(InvitationCode).order_by(InvitationCode.created_at.desc()).limit(limit)
        ).all()
    )


def revoke(session: Session, code_id: str) -> None:
    changed = session.execute(
        update(InvitationCode)
        .where(InvitationCode.id == code_id, InvitationCode.revoked_at.is_(None))
        .values(revoked_at=utc_now())
    )
    session.commit()
    if changed.rowcount != 1:
        raise DomainError("INVITATION_CODE_INVALID")


def is_usable(row: InvitationCode, now: datetime | None = None) -> bool:
    moment = now or utc_now()
    if row.used_at is not None or row.revoked_at is not None:
        return False
    return row.expires_at is None or row.expires_at > moment
