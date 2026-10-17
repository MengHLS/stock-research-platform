import pytest

from research_platform.core.config import Settings
from research_platform.main import create_app


def test_health_is_real_and_private_routes_fail_closed(client_factory):
    client = client_factory()
    assert client.get("/health/live").json()["status"] == "ok"
    assert client.get("/health/ready").status_code == 200
    denied = client.get("/api/v1/catalog")
    assert denied.status_code == 503
    assert denied.json()["detail"]["code"] == "AUTH_NOT_CONFIGURED"


def test_production_cannot_boot_without_authentication():
    with pytest.raises(RuntimeError, match="Production is blocked"):
        create_app(Settings(environment="production", database_url="sqlite://", _env_file=None))


def test_two_users_cannot_read_each_others_entries_or_counts(client_factory):
    alice, bob = client_factory(1), client_factory(2)
    response = alice.post("/api/v1/catalog", json={"name": "私人研究"})
    assert response.status_code == 201
    entry = response.json()
    assert alice.get(f"/api/v1/catalog/{entry['id']}").status_code == 200
    assert bob.get(f"/api/v1/catalog/{entry['id']}").status_code == 404
    assert bob.get("/api/v1/catalog").json()["total"] == 0
    assert alice.get("/api/v1/catalog").json()["total"] == 1
    assert alice.get("/api/v1/catalog/not-an-entry").status_code == 404


def test_client_cannot_assign_an_owner_and_pagination_is_bounded(client_factory):
    client = client_factory(1)
    assert (
        client.post("/api/v1/catalog", json={"name": "forged", "owner_user_id": 2}).status_code
        == 422
    )
    assert client.post("/api/v1/catalog", json={"name": "   "}).status_code == 422
    assert client.get("/api/v1/catalog?limit=100000").status_code == 422


def test_job_idempotency_and_user_isolation(client_factory):
    alice, bob = client_factory(1), client_factory(2)
    payload = {"job_type": "system.check", "idempotency_key": "same-request-key"}
    first = alice.post("/api/v1/jobs", json=payload)
    repeated = alice.post("/api/v1/jobs", json=payload)
    assert first.status_code == repeated.status_code == 202
    assert first.json()["id"] == repeated.json()["id"]
    assert bob.get(f"/api/v1/jobs/{first.json()['id']}").status_code == 404
    assert bob.post("/api/v1/jobs", json=payload).json()["id"] != first.json()["id"]
    assert (
        alice.post(
            "/api/v1/jobs", json={"job_type": "execute-any-file", "idempotency_key": "evil-command"}
        ).status_code
        == 422
    )
