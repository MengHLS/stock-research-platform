"""User, session and login-audit tables.

Design notes, ported from the legacy project's ``users`` table but extended for
self-hosted registration/login (the legacy app delegated identity to an OAuth
provider and only stored ``openId``):

- ``user_account`` keeps credentials separate from profile so a password reset
  never touches profile data, and so future SSO can attach without rewriting the
  identity row;
- e-mail is the login identifier and is stored lower-cased, with a unique index
  that is case-insensitive by construction (the application normalizes first);
- ``user_session`` stores only a **hash** of the session token. A database leak
  therefore cannot be replayed as a live session, which is the point of using an
  opaque token instead of a self-contained JWT;
- ``login_attempt`` is a bounded audit of failures, used for lockout. It records
  no password material and no raw token.
"""

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from research_platform.core.database import Base


def utc_now() -> datetime:
    """Naive UTC in the database; the API layer adds the timezone on output."""
    return datetime.now(UTC).replace(tzinfo=None)


class UserAccount(Base):
    """Identity row: who the user is and whether the account may sign in."""

    __tablename__ = "user_account"
    __table_args__ = (Index("ix_user_account_email", "email", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="user", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )
    last_signed_in_at: Mapped[datetime | None] = mapped_column(DateTime)


class UserCredential(Base):
    """Password material, kept out of the identity row.

    ``password_hash`` uses the ``scrypt$<n>$<r>$<p>$<salt>$<hash>`` encoding so the
    parameters travel with the hash and can be upgraded later without a migration.
    """

    __tablename__ = "user_credential"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user_account.id", ondelete="CASCADE"), primary_key=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    password_updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)


class UserSession(Base):
    """Server-side session: only the token hash is stored.

    Logout and password change delete rows, so revocation is immediate. A stolen
    token hash cannot be turned back into a usable token.
    """

    __tablename__ = "user_session"
    __table_args__ = (
        Index("ix_user_session_token", "token_hash", unique=True),
        Index("ix_user_session_user", "user_id", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    user_agent: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    ip_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)


class LoginAttempt(Base):
    """Bounded audit of sign-in attempts (no password, no token)."""

    __tablename__ = "login_attempt"
    __table_args__ = (Index("ix_login_attempt_email", "email", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)


class InvitationCode(Base):
    """A single-use registration code.

    The code is the gate for self-registration when the operator wants to vet
    every account: knowing a valid code *is* the approval, so no separate review
    state is needed for one or two users.

    Only a hash of the code is stored, for the same reason as session tokens: a
    database leak must not yield working codes. ``used_by_user_id`` records who
    consumed it, so an operator can see which account a code produced.
    """

    __tablename__ = "invitation_code"
    __table_args__ = (
        Index("ix_invitation_code_hash", "code_hash", unique=True),
        Index("ix_invitation_code_state", "used_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # A short, non-secret label so the operator can tell codes apart in a list.
    label: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime)
    used_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user_account.id", ondelete="SET NULL")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
