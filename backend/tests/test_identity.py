"""Registration, login, session and lockout behaviour.

These assertions are about observable HTTP/auth behaviour, not internals: what a
client can do, what it is refused, and what must never leak. The database-backed
fixtures run the real migrations, so the identity migration is exercised too.
"""

from __future__ import annotations

import pytest

from research_platform.core.config import Settings
from research_platform.main import create_app
from research_platform.modules.identity import service
from research_platform.modules.identity.security import (
    hash_password,
    hash_session_token,
    verify_password,
)

SECRET = "test-secret-value-that-is-long-enough-32+"


def auth_settings(database_url, **auth_overrides):
    auth = {"secret": SECRET, "cookie_secure": False, "allow_registration": True}
    auth.update(auth_overrides)
    return Settings(environment="test", database_url=database_url, auth=auth, _env_file=None)


@pytest.fixture
def auth_client_factory(database_url):
    from fastapi.testclient import TestClient

    clients = []

    def make(**auth_overrides):
        app = create_app(auth_settings(database_url, **auth_overrides))
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)


# --- primitives -----------------------------------------------------------


def test_password_hash_is_not_reversible_and_verifies():
    encoded = hash_password("correct horse battery staple")
    assert encoded.startswith("scrypt$")
    assert "correct horse battery staple" not in encoded
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong password", encoded)


def test_malformed_hash_verifies_as_false_instead_of_raising():
    assert not verify_password("x", "not-a-valid-encoding")
    assert not verify_password("x", "bcrypt$1$2$3$4$5")
    assert not verify_password("x", "scrypt$bad$8$1$00$00")


def test_same_password_hashes_differently_due_to_salt():
    assert hash_password("same-password") != hash_password("same-password")


def test_session_token_hash_is_stable_and_not_the_token():
    token = "opaque-session-value"
    assert hash_session_token(token) == hash_session_token(token)
    assert token not in hash_session_token(token)


# --- registration ---------------------------------------------------------


def test_register_signs_in_and_returns_no_credential_material(auth_client_factory):
    client = auth_client_factory()
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "Alice@Example.COM", "password": "a-long-password", "display_name": "Alice"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == "alice@example.com"
    assert body["user"]["role"] == "user"
    assert "password" not in response.text.lower()
    assert "scrypt" not in response.text
    # The cookie is HttpOnly: the client keeps it, but it is not in the body.
    assert client.cookies.get("rp_session")


def test_email_is_normalized_so_case_does_not_create_duplicates(auth_client_factory):
    client = auth_client_factory()
    first = client.post(
        "/api/v1/auth/register", json={"email": "bob@example.com", "password": "a-long-password"}
    )
    assert first.status_code == 201
    duplicate = client.post(
        "/api/v1/auth/register", json={"email": "BOB@example.com", "password": "a-long-password"}
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "EMAIL_ALREADY_REGISTERED"


def test_registration_can_be_closed(auth_client_factory):
    client = auth_client_factory(allow_registration=False)
    response = client.post(
        "/api/v1/auth/register", json={"email": "x@example.com", "password": "a-long-password"}
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "REGISTRATION_CLOSED"


def test_short_password_is_refused(auth_client_factory):
    client = auth_client_factory()
    response = client.post(
        "/api/v1/auth/register", json={"email": "x@example.com", "password": "short"}
    )
    assert response.status_code == 422


def test_client_cannot_choose_its_role_or_id(auth_client_factory):
    client = auth_client_factory()
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "z@example.com",
            "password": "a-long-password",
            "role": "admin",
            "id": 1,
        },
    )
    assert response.status_code == 422


# --- login ----------------------------------------------------------------


def test_login_works_and_logout_revokes_the_session(auth_client_factory):
    client = auth_client_factory()
    client.post(
        "/api/v1/auth/register", json={"email": "u@example.com", "password": "a-long-password"}
    )
    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/auth/session").json() is None

    login = client.post(
        "/api/v1/auth/login", json={"email": "U@example.com", "password": "a-long-password"}
    )
    assert login.status_code == 200
    assert client.get("/api/v1/auth/session").json()["user"]["email"] == "u@example.com"


def test_wrong_password_and_unknown_email_are_indistinguishable(auth_client_factory):
    client = auth_client_factory()
    client.post(
        "/api/v1/auth/register", json={"email": "known@example.com", "password": "a-long-password"}
    )
    client.post("/api/v1/auth/logout")
    wrong = client.post(
        "/api/v1/auth/login", json={"email": "known@example.com", "password": "wrong-password"}
    )
    unknown = client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong-password"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"]["code"] == unknown.json()["detail"]["code"]


def test_lockout_after_repeated_failures(auth_client_factory):
    client = auth_client_factory(max_failed_logins=3, lockout_minutes=15)
    client.post(
        "/api/v1/auth/register", json={"email": "lock@example.com", "password": "a-long-password"}
    )
    client.post("/api/v1/auth/logout")
    for _ in range(3):
        client.post(
            "/api/v1/auth/login", json={"email": "lock@example.com", "password": "bad-password"}
        )
    blocked = client.post(
        "/api/v1/auth/login", json={"email": "lock@example.com", "password": "a-long-password"}
    )
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["code"] == "ACCOUNT_LOCKED"


def test_inactive_account_cannot_sign_in(auth_client_factory, session):
    from sqlalchemy import select

    from research_platform.modules.identity.models import UserAccount

    client = auth_client_factory()
    client.post(
        "/api/v1/auth/register", json={"email": "off@example.com", "password": "a-long-password"}
    )
    account = session.scalar(select(UserAccount).where(UserAccount.email == "off@example.com"))
    account.is_active = False
    session.commit()
    client.post("/api/v1/auth/logout")
    response = client.post(
        "/api/v1/auth/login", json={"email": "off@example.com", "password": "a-long-password"}
    )
    assert response.status_code == 401


# --- session resolution ---------------------------------------------------


def test_session_cookie_is_required_and_forged_tokens_are_refused(auth_client_factory):
    client = auth_client_factory()
    client.post(
        "/api/v1/auth/register", json={"email": "s@example.com", "password": "a-long-password"}
    )
    stolen = client.cookies.get("rp_session")
    client.cookies.set("rp_session", "forged-token-value")
    assert client.get("/api/v1/auth/session").json() is None
    client.cookies.set("rp_session", stolen)
    assert client.get("/api/v1/auth/session").json() is not None


def test_expired_session_is_rejected(auth_client_factory, session, database_url):
    from datetime import timedelta

    from sqlalchemy import select

    from research_platform.modules.identity.models import UserSession, utc_now

    client = auth_client_factory()
    client.post(
        "/api/v1/auth/register", json={"email": "e@example.com", "password": "a-long-password"}
    )
    row = session.scalar(select(UserSession))
    row.expires_at = utc_now() - timedelta(minutes=1)
    session.commit()
    assert client.get("/api/v1/auth/session").json() is None


def test_private_route_now_requires_login(auth_client_factory):
    """The catalog was previously unreachable (AUTH_NOT_CONFIGURED); now it needs a session."""
    client = auth_client_factory()
    anonymous = client.get("/api/v1/catalog")
    assert anonymous.status_code == 401
    assert anonymous.json()["detail"]["code"] == "AUTHENTICATION_REQUIRED"

    client.post(
        "/api/v1/auth/register", json={"email": "c@example.com", "password": "a-long-password"}
    )
    assert client.get("/api/v1/catalog").status_code == 200


def test_two_users_are_isolated(auth_client_factory):
    alice, bob = auth_client_factory(), auth_client_factory()
    alice.post(
        "/api/v1/auth/register", json={"email": "alice@example.com", "password": "a-long-password"}
    )
    bob.post(
        "/api/v1/auth/register", json={"email": "bob@example.com", "password": "a-long-password"}
    )
    created = alice.post("/api/v1/catalog", json={"name": "alice private"})
    assert created.status_code == 201
    entry_id = created.json()["id"]
    assert alice.get(f"/api/v1/catalog/{entry_id}").status_code == 200
    assert bob.get(f"/api/v1/catalog/{entry_id}").status_code == 404
    assert bob.get("/api/v1/catalog").json()["total"] == 0
    assert alice.get("/api/v1/catalog").json()["total"] == 1


# --- password change ------------------------------------------------------


def test_password_change_revokes_other_sessions(auth_client_factory):
    first, second = auth_client_factory(), auth_client_factory()
    first.post(
        "/api/v1/auth/register", json={"email": "p@example.com", "password": "a-long-password"}
    )
    token = first.cookies.get("rp_session")
    second.cookies.set("rp_session", token)
    assert second.get("/api/v1/auth/session").json() is not None

    changed = first.post(
        "/api/v1/auth/password",
        json={"current_password": "a-long-password", "new_password": "another-long-password"},
    )
    assert changed.status_code == 204
    # Every session, including the one that changed it, is revoked.
    assert second.get("/api/v1/auth/session").json() is None
    assert first.get("/api/v1/auth/session").json() is None

    relogin = first.post(
        "/api/v1/auth/login", json={"email": "p@example.com", "password": "another-long-password"}
    )
    assert relogin.status_code == 200


def test_password_change_requires_the_current_password(auth_client_factory):
    client = auth_client_factory()
    client.post(
        "/api/v1/auth/register", json={"email": "q@example.com", "password": "a-long-password"}
    )
    response = client.post(
        "/api/v1/auth/password",
        json={"current_password": "wrong-password", "new_password": "another-long-password"},
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "INVALID_CREDENTIALS"


# --- configuration guards -------------------------------------------------


def test_auth_endpoints_fail_closed_without_configuration(database_url):
    from fastapi.testclient import TestClient

    app = create_app(Settings(environment="test", database_url=database_url, _env_file=None))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/login", json={"email": "a@example.com", "password": "a-long-password"}
        )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "AUTH_NOT_CONFIGURED"


def test_login_attempts_are_recorded_without_credentials(auth_client_factory, session):
    from sqlalchemy import select

    from research_platform.modules.identity.models import LoginAttempt

    client = auth_client_factory()
    client.post(
        "/api/v1/auth/register", json={"email": "audit@example.com", "password": "a-long-password"}
    )
    attempts = session.scalars(select(LoginAttempt)).all()
    assert attempts
    for attempt in attempts:
        assert "a-long-password" not in (attempt.reason + attempt.email)


def test_service_rejects_login_when_locked_even_with_correct_password(session, database_url):
    """Lockout is enforced in the service, not only by the HTTP layer."""
    from research_platform.core.config import AuthConfig

    config = AuthConfig(secret=SECRET, max_failed_logins=1, lockout_minutes=15)
    service.register(session, config, email="svc@example.com", password="a-long-password")
    from research_platform.core.errors import DomainError

    with pytest.raises(DomainError) as rejected:
        service.login(session, config, email="svc@example.com", password="wrong-password")
    assert rejected.value.code == "INVALID_CREDENTIALS"
    with pytest.raises(DomainError) as locked:
        service.login(session, config, email="svc@example.com", password="a-long-password")
    assert locked.value.code == "ACCOUNT_LOCKED"
