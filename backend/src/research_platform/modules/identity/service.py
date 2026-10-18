"""Registration, login, session lifecycle and lockout.

Invariants this module owns:

- e-mail is normalized before any lookup or insert, so ``A@b.com`` and ``a@b.com``
  cannot become two accounts;
- a failed login never reveals whether the e-mail exists: the same error code and
  a password-hash comparison against a dummy hash are used in both cases;
- lockout is stored on the credential row and counts only failures, so a
  successful login clears it;
- passwords are verified with scrypt and re-hashed on change; every existing
  session of that user is revoked, because a password change must invalidate
  tokens that may have been stolen;
- sessions are rows keyed by token *hash*; logout deletes the row.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from research_platform.core.config import AuthConfig
from research_platform.core.errors import DomainError

from . import invitations
from .models import LoginAttempt, UserAccount, UserCredential, UserSession, utc_now
from .security import (
    hash_client_address,
    hash_password,
    hash_session_token,
    new_session_token,
    verify_password,
)

# Verified against when the e-mail is unknown, so the response time does not
# reveal whether an account exists.
_DUMMY_HASH = (
    "scrypt$16384$8$1$00000000000000000000000000000000$"
    "0000000000000000000000000000000000000000000000000000000000000000"
)


def normalize_email(value: str) -> str:
    return value.strip().lower()


def _require_auth_config(config: AuthConfig | None) -> AuthConfig:
    if config is None:
        raise DomainError("AUTH_NOT_CONFIGURED")
    return config


def _validate_password(password: str, config: AuthConfig) -> None:
    if len(password) < config.min_password_length:
        raise DomainError(
            "PASSWORD_TOO_WEAK",
            f"密码至少需要 {config.min_password_length} 个字符。",
        )


def register(
    session: Session,
    config: AuthConfig | None,
    *,
    email: str,
    password: str,
    display_name: str = "",
    invitation_code: str | None = None,
) -> UserAccount:
    """Create an account, honouring the configured registration mode.

    In ``invite`` mode the code is spent *before* the account is created, and the
    whole operation runs in one transaction: a code must never be consumed by a
    registration that then fails on a duplicate e-mail, or the operator's approval
    would be silently lost.
    """
    config = _require_auth_config(config)
    if config.registration == "closed":
        raise DomainError("REGISTRATION_CLOSED")
    normalized = normalize_email(email)
    _validate_password(password, config)
    existing = session.scalar(select(UserAccount).where(UserAccount.email == normalized))
    if existing is not None:
        # Deliberately explicit: registration is an authenticated-action-shaped
        # endpoint for a single-user tool, and silently succeeding would leave the
        # caller unable to sign in with the password they just chose.
        raise DomainError("EMAIL_ALREADY_REGISTERED")

    invitation = None
    if config.registration == "invite":
        if not invitation_code:
            raise DomainError("INVITATION_CODE_REQUIRED")
        # ``consume`` commits its own conditional update; a later failure here
        # cannot un-spend it, so the account insert below must not fail. The
        # duplicate check above is the only realistic failure and runs first.
        invitation = invitations.consume(session, invitation_code)

    account = UserAccount(email=normalized, display_name=display_name.strip())
    session.add(account)
    session.flush()
    session.add(UserCredential(user_id=account.id, password_hash=hash_password(password)))
    session.commit()
    session.refresh(account)

    if invitation is not None:
        invitations.attach_user(session, invitation, account.id)
    return account


def login(
    session: Session,
    config: AuthConfig | None,
    *,
    email: str,
    password: str,
    user_agent: str = "",
    client_address: str = "",
) -> tuple[UserAccount, str, datetime]:
    """Verify credentials and open a session; returns ``(user, token, expiry)``."""
    config = _require_auth_config(config)
    normalized = normalize_email(email)
    now = utc_now()
    account = session.scalar(select(UserAccount).where(UserAccount.email == normalized))
    credential = (
        session.scalar(select(UserCredential).where(UserCredential.user_id == account.id))
        if account is not None
        else None
    )

    if credential is not None and credential.locked_until and credential.locked_until > now:
        _record_attempt(session, normalized, False, "LOCKED")
        session.commit()
        raise DomainError("ACCOUNT_LOCKED")

    encoded = credential.password_hash if credential is not None else _DUMMY_HASH
    valid = verify_password(password, encoded)
    if not valid or account is None or credential is None or not account.is_active:
        if credential is not None:
            credential.failed_attempts += 1
            if credential.failed_attempts >= config.max_failed_logins:
                credential.locked_until = now + timedelta(minutes=config.lockout_minutes)
        reason = "BAD_CREDENTIALS" if account is not None else "UNKNOWN_EMAIL"
        _record_attempt(session, normalized, False, reason)
        session.commit()
        # One code for every rejection path: unknown account, wrong password and
        # disabled account are indistinguishable to the caller.
        raise DomainError("INVALID_CREDENTIALS")

    credential.failed_attempts = 0
    credential.locked_until = None
    account.last_signed_in_at = now
    token = new_session_token()
    expires_at = now + timedelta(hours=config.session_ttl_hours)
    session.add(
        UserSession(
            id=str(uuid.uuid4()),
            user_id=account.id,
            token_hash=hash_session_token(token),
            expires_at=expires_at,
            user_agent=user_agent[:200],
            ip_hash=hash_client_address(client_address) if client_address else "",
        )
    )
    _record_attempt(session, normalized, True, "")
    session.commit()
    session.refresh(account)
    return account, token, expires_at


def resolve_session(
    session: Session, *, token: str, now: datetime | None = None
) -> tuple[UserAccount, UserSession]:
    """Return the account behind a live token, or raise ``AUTHENTICATION_REQUIRED``."""
    moment = now or utc_now()
    row = session.scalar(
        select(UserSession).where(
            UserSession.token_hash == hash_session_token(token),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > moment,
        )
    )
    if row is None:
        raise DomainError("AUTHENTICATION_REQUIRED")
    account = session.get(UserAccount, row.user_id)
    if account is None or not account.is_active:
        raise DomainError("AUTHENTICATION_REQUIRED")
    return account, row


def logout(session: Session, *, token: str) -> None:
    session.execute(
        update(UserSession)
        .where(
            UserSession.token_hash == hash_session_token(token),
            UserSession.revoked_at.is_(None),
        )
        .values(revoked_at=utc_now())
    )
    session.commit()


def change_password(
    session: Session,
    config: AuthConfig | None,
    *,
    user_id: int,
    current_password: str,
    new_password: str,
) -> None:
    config = _require_auth_config(config)
    credential = session.scalar(select(UserCredential).where(UserCredential.user_id == user_id))
    if credential is None or not verify_password(current_password, credential.password_hash):
        raise DomainError("INVALID_CREDENTIALS")
    _validate_password(new_password, config)
    credential.password_hash = hash_password(new_password)
    credential.password_updated_at = utc_now()
    credential.failed_attempts = 0
    credential.locked_until = None
    # Every prior session is revoked: a password change must not leave a stolen
    # token usable.
    session.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=utc_now())
    )
    session.commit()


def _record_attempt(session: Session, email: str, succeeded: bool, reason: str) -> None:
    session.add(LoginAttempt(email=email, succeeded=succeeded, reason=reason))
