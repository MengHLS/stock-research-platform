"""Contract tests for the single public error body.

Every failure path must produce the same ``{"detail": {code, message, request_id}}``
document on its real HTTP status, with the status coming from the explicit table in
``core.errors`` and a request id matching the ``X-Request-ID`` response header.
Only tests live here; the implementation is not modified.
"""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from research_platform.core.config import Settings
from research_platform.core.error_handlers import error_response, route_template
from research_platform.core.errors import (
    DEFAULT_ERROR_RESPONSES,
    ERROR_SPECS,
    FALLBACK_SPEC,
    STATUS_CODES,
    DomainError,
    ErrorDetail,
    ErrorField,
    ErrorResponse,
    http_status_for,
    spec_for,
)
from research_platform.core.logging import request_scope
from research_platform.main import create_app

REQUEST_ID_HEADER = "X-Request-ID"
DETAIL_KEYS = {"code", "message", "request_id"}


def detail_of(response):
    body = response.json()
    assert set(body) == {"detail"}
    return body["detail"]


def assert_correlated(response, expected_code):
    detail = detail_of(response)
    request_id = response.headers.get(REQUEST_ID_HEADER)
    assert request_id, "every response must carry X-Request-ID"
    assert detail["request_id"] == request_id
    assert detail["code"] == expected_code
    assert isinstance(detail["message"], str) and detail["message"]
    return detail


def test_unknown_route_and_wrong_method_use_the_shared_error_body(client_factory):
    client = client_factory()

    unknown = client.get("/api/v1/does-not-exist")
    assert unknown.status_code == 404
    assert unknown.headers["content-type"].startswith("application/json")
    unknown_detail = assert_correlated(unknown, "ROUTE_NOT_FOUND")
    assert set(unknown_detail) == DETAIL_KEYS
    assert "fields" not in unknown_detail
    assert unknown_detail["message"] == spec_for("ROUTE_NOT_FOUND").message

    wrong_method = client.put("/health/live")
    assert wrong_method.status_code == 405
    method_detail = assert_correlated(wrong_method, "METHOD_NOT_ALLOWED")
    assert set(method_detail) == DETAIL_KEYS
    assert wrong_method.headers[REQUEST_ID_HEADER] != unknown.headers[REQUEST_ID_HEADER]


def test_validation_errors_expose_paths_and_codes_but_never_raw_input(client_factory):
    client = client_factory(1)

    invalid = client.post(
        "/api/v1/catalog",
        json={"name": "", "owner_user_id": "MARKER-RAW-OWNER", "extra": "MARKER-RAW-EXTRA"},
    )
    assert invalid.status_code == 422
    detail = assert_correlated(invalid, "VALIDATION_FAILED")
    assert detail["fields"]
    for field in detail["fields"]:
        assert set(field) == {"path", "code"}
        assert isinstance(field["path"], str) and field["path"]
        assert isinstance(field["code"], str) and field["code"]
    paths = {field["path"]: field["code"] for field in detail["fields"]}
    assert paths["name"] == "string_too_short"
    assert paths["owner_user_id"] == "extra_forbidden"
    for marker in ("MARKER-RAW-OWNER", "MARKER-RAW-EXTRA", "input", "msg", "ctx"):
        assert marker not in invalid.text

    bounded = client.get("/api/v1/catalog?limit=100000")
    assert bounded.status_code == 422
    bounded_detail = assert_correlated(bounded, "VALIDATION_FAILED")
    assert bounded_detail["fields"] == [{"path": "query.limit", "code": "less_than_equal"}]
    assert "100000" not in bounded.text


def test_business_errors_keep_real_status_and_matching_request_id(client_factory):
    user = client_factory(1)
    entry = user.get("/api/v1/catalog/not-an-entry")
    assert entry.status_code == 404
    entry_detail = assert_correlated(entry, "ENTRY_NOT_FOUND")
    assert set(entry_detail) == DETAIL_KEYS
    assert entry_detail["message"] == spec_for("ENTRY_NOT_FOUND").message

    job = user.get("/api/v1/jobs/not-a-job")
    assert job.status_code == 404
    assert_correlated(job, "JOB_NOT_FOUND")

    anonymous = client_factory()
    denied = anonymous.get("/api/v1/catalog")
    assert denied.status_code == 503
    denied_detail = assert_correlated(denied, "AUTH_NOT_CONFIGURED")
    assert set(denied_detail) == DETAIL_KEYS

    request_ids = {
        entry.headers[REQUEST_ID_HEADER],
        job.headers[REQUEST_ID_HEADER],
        denied.headers[REQUEST_ID_HEADER],
    }
    assert len(request_ids) == 3


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("REQUEST_INVALID", 400),
        ("AUTHENTICATION_REQUIRED", 401),
        ("PERMISSION_DENIED", 403),
        ("ENTRY_NOT_FOUND", 404),
        ("JOB_NOT_FOUND", 404),
        ("ROUTE_NOT_FOUND", 404),
        ("METHOD_NOT_ALLOWED", 405),
        ("IDEMPOTENCY_CONFLICT", 409),
        ("VALIDATION_FAILED", 422),
        ("RATE_LIMITED", 429),
        ("INTERNAL_ERROR", 500),
        ("AUTH_NOT_CONFIGURED", 503),
        ("SERVICE_UNAVAILABLE", 503),
        ("SOURCE_NOT_CONFIGURED", 503),
        ("MARKET_REVIEW_RANGE_INVALID", 400),
        ("MARKET_REVIEW_DATE_UNAVAILABLE", 404),
        ("MARKET_REVIEW_SOURCE_UNAVAILABLE", 503),
        ("MARKET_REVIEW_SOURCE_AUTH_FAILED", 503),
        ("MARKET_REVIEW_SOURCE_BAD_DATA", 502),
        ("DATABASE_UNAVAILABLE", 503),
    ],
)
def test_http_status_comes_from_the_explicit_table(code, status):
    assert http_status_for(code) == status
    assert spec_for(code).status == status


def test_error_specs_table_is_internally_consistent():
    for key, spec in ERROR_SPECS.items():
        assert spec.code == key
        assert http_status_for(key) == spec.status
        assert 400 <= spec.status < 600
        assert spec.message.strip()
    assert set(STATUS_CODES.values()) <= set(ERROR_SPECS)
    assert set(DEFAULT_ERROR_RESPONSES) == set(STATUS_CODES)


def test_unmapped_code_falls_back_to_400_without_suffix_guessing():
    assert spec_for("NOT_A_REAL_CODE") is FALLBACK_SPEC
    assert FALLBACK_SPEC.status == 400
    assert http_status_for("SOMETHING_NOT_FOUND") == 400
    assert http_status_for("MADE_UP_CONFLICT") == 400

    with request_scope("fallback-request"):
        response = error_response("MADE_UP_CODE")
    assert response.status_code == 400
    body = json.loads(response.body)
    assert body["detail"]["code"] == "REQUEST_INVALID"
    assert body["detail"]["request_id"] == "fallback-request"


def test_error_response_builder_omits_empty_fields_and_keeps_shape():
    with request_scope("fixed-request-id"):
        plain = error_response("ENTRY_NOT_FOUND")
    assert plain.status_code == 404
    assert json.loads(plain.body) == {
        "detail": {
            "code": "ENTRY_NOT_FOUND",
            "message": spec_for("ENTRY_NOT_FOUND").message,
            "request_id": "fixed-request-id",
        }
    }

    with request_scope("second-request-id"):
        with_fields = error_response(
            "VALIDATION_FAILED",
            message="custom message",
            fields=[ErrorField(path="name", code="string_too_short")],
        )
    assert with_fields.status_code == 422
    assert json.loads(with_fields.body) == {
        "detail": {
            "code": "VALIDATION_FAILED",
            "message": "custom message",
            "request_id": "second-request-id",
            "fields": [{"path": "name", "code": "string_too_short"}],
        }
    }


def test_route_template_never_returns_the_concrete_path():
    matched = SimpleNamespace(scope={"route": SimpleNamespace(path="/api/v1/catalog/{entry_id}")})
    assert route_template(matched) == "/api/v1/catalog/{entry_id}"
    assert route_template(SimpleNamespace(scope={"route": None})) == "unmatched"
    assert route_template(SimpleNamespace(scope={})) == "unmatched"


def test_domain_error_defaults_to_the_reviewed_message():
    error = DomainError("ENTRY_NOT_FOUND")
    assert error.code == "ENTRY_NOT_FOUND"
    assert error.spec.status == 404
    assert error.message == spec_for("ENTRY_NOT_FOUND").message
    assert error.fields == []
    assert str(error) == error.message

    custom = DomainError(
        "IDEMPOTENCY_CONFLICT",
        "specific message",
        fields=[ErrorField(path="idempotency_key", code="conflict")],
    )
    assert custom.spec.status == 409
    assert custom.message == "specific message"
    assert custom.fields == [ErrorField(path="idempotency_key", code="conflict")]

    unmapped = DomainError("STILL_UNMAPPED")
    assert unmapped.spec is FALLBACK_SPEC
    assert unmapped.message == FALLBACK_SPEC.message


def test_error_models_forbid_extra_fields_and_omit_unset_optional_values():
    detail = ErrorDetail(code="ENTRY_NOT_FOUND", message="missing")
    assert detail.model_dump(exclude_none=True) == {"code": "ENTRY_NOT_FOUND", "message": "missing"}
    body = ErrorResponse(detail=detail).model_dump(exclude_none=True)
    assert body == {"detail": {"code": "ENTRY_NOT_FOUND", "message": "missing"}}

    with pytest.raises(ValueError):
        ErrorDetail(code="ENTRY_NOT_FOUND", message="missing", input="RAW")
    with pytest.raises(ValueError):
        ErrorField(path="name", code="bad", msg="RAW")


def test_documented_error_surface_matches_the_status_table():
    for entry in DEFAULT_ERROR_RESPONSES.values():
        assert entry["model"] is ErrorResponse
        assert entry["description"]

    app = create_app(Settings(environment="test", database_url="sqlite://", _env_file=None))
    document = app.openapi()
    documented = document["paths"]["/health/live"]["get"]["responses"]
    for status in STATUS_CODES:
        schema = documented[str(status)]["content"]["application/json"]["schema"]
        assert schema == {"$ref": "#/components/schemas/ErrorResponse"}
    assert "ErrorResponse" in document["components"]["schemas"]


def test_unhandled_exception_returns_a_fixed_safe_body():
    app = create_app(Settings(environment="test", database_url="sqlite://", _env_file=None))

    @app.get("/boom")
    def boom():
        raise RuntimeError(
            "MARKER_EXCEPTION SELECT * FROM users password=hunter2 C:/secret/path.py"
        )

    with TestClient(app) as client:
        response = client.get("/boom")

    assert response.status_code == 500
    detail = assert_correlated(response, "INTERNAL_ERROR")
    assert set(detail) == DETAIL_KEYS
    assert detail["message"] == spec_for("INTERNAL_ERROR").message
    assert detail["message"] == "服务内部错误，请稍后重试。"
    for marker in (
        "Traceback",
        "MARKER_EXCEPTION",
        "SELECT * FROM",
        "hunter2",
        "C:/secret/path.py",
        "RuntimeError",
    ):
        assert marker not in response.text
