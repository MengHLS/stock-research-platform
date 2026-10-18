"""Verification for structured request logging, correlation and redaction.

The logger is observed through a handler attached to the ``research_platform``
logger: every emitted record's message is the rendered JSON document, which is
exactly what a stdout consumer sees. A second, unit-level layer asserts the
redaction helpers directly so a regression is localised without a running app.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from research_platform.core.config import Settings
from research_platform.core.logging import (
    EVENT_LOGGER,
    MAX_TEXT,
    REDACTED,
    REDACTED_URL,
    ROLE_API,
    error_fields,
    job_scope,
    log_event,
    request_scope,
    safe_headers,
    sanitize,
    sanitize_text,
    sanitize_value,
)
from research_platform.main import create_app

REQUEST_ID_HEADER = "X-Request-ID"


class _Sink(logging.Handler):
    """Collect our structured events; ids let a test slice one request."""

    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record):
        self.records.append(record)

    def events(self, start=0):
        return [json.loads(record.getMessage()) for record in self.records[start:]]

    def lines(self, start=0):
        return [record.getMessage() for record in self.records[start:]]


@pytest.fixture
def log_sink():
    logger = logging.getLogger(EVENT_LOGGER)
    sink = _Sink()
    previous_level = logger.level
    previous_propagate = logger.propagate
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger.addHandler(sink)
    try:
        yield sink
    finally:
        logger.removeHandler(sink)
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate


def only_event(events, name):
    matches = [event for event in events if event["event"] == name]
    assert len(matches) == 1, [event["event"] for event in events]
    return matches[0]


def test_completed_event_carries_method_route_status_duration_and_request_id(
    client_factory, log_sink
):
    client = client_factory()
    start = len(log_sink.records)

    response = client.get("/health/live")
    assert response.status_code == 200

    events = log_sink.events(start)
    completed = only_event(events, "request.completed")
    assert completed["request_id"] == response.headers[REQUEST_ID_HEADER]
    assert completed["method"] == "GET"
    assert completed["route"] == "/health/live"
    assert completed["status"] == 200
    assert completed["error_code"] is None
    assert isinstance(completed["duration_ms"], float)
    assert completed["duration_ms"] >= 0
    assert completed["duration_ms"] == round(completed["duration_ms"], 1)
    assert completed["level"] == "INFO"
    assert completed["role"] == ROLE_API
    assert not any(event["event"] == "request.failed" for event in events)


def test_unmatched_route_is_logged_as_constant_not_the_concrete_path(client_factory, log_sink):
    client = client_factory()
    start = len(log_sink.records)
    marker = "MARKER-ROUTE-PATH"

    response = client.get(f"/api/v1/{marker}")
    assert response.status_code == 404

    events = log_sink.events(start)
    completed = only_event(events, "request.completed")
    assert completed["route"] == "unmatched"
    assert completed["status"] == 404
    assert completed["error_code"] == "ROUTE_NOT_FOUND"
    assert completed["request_id"] == response.headers[REQUEST_ID_HEADER]
    for line in log_sink.lines(start):
        assert marker not in line


def test_route_template_replaces_concrete_ids_in_the_log(client_factory, log_sink):
    client = client_factory(1)
    marker = "MARKER-ENTRY-ID"
    start = len(log_sink.records)

    response = client.get(f"/api/v1/catalog/{marker}")
    assert response.status_code == 404

    events = log_sink.events(start)
    completed = only_event(events, "request.completed")
    assert completed["route"] == "/api/v1/catalog/{entry_id}"
    assert completed["error_code"] == "ENTRY_NOT_FOUND"
    assert completed["request_id"] == response.headers[REQUEST_ID_HEADER]
    for line in log_sink.lines(start):
        assert marker not in line


@pytest.mark.parametrize(
    ("method", "path", "status", "error_code"),
    [
        ("get", "/api/v1/nope", 404, "ROUTE_NOT_FOUND"),
        ("put", "/health/live", 405, "METHOD_NOT_ALLOWED"),
        ("get", "/api/v1/jobs/does-not-exist", 404, "JOB_NOT_FOUND"),
    ],
)
def test_error_status_and_code_are_derived_from_one_table(
    client_factory, log_sink, method, path, status, error_code
):
    client = client_factory(1)
    start = len(log_sink.records)

    response = getattr(client, method)(path)
    assert response.status_code == status

    completed = only_event(log_sink.events(start), "request.completed")
    assert completed["status"] == status
    assert completed["error_code"] == error_code
    assert completed["request_id"] == response.headers[REQUEST_ID_HEADER]


def test_method_not_allowed_on_a_template_route_keeps_the_template(client_factory, log_sink):
    client = client_factory(1)
    marker = "MARKER-METHOD-ID"
    start = len(log_sink.records)

    response = client.put(f"/api/v1/catalog/{marker}")
    assert response.status_code == 405

    completed = only_event(log_sink.events(start), "request.completed")
    assert completed["route"] == "/api/v1/catalog/{entry_id}"
    assert completed["status"] == 405
    assert completed["error_code"] == "METHOD_NOT_ALLOWED"
    assert completed["request_id"] == response.headers[REQUEST_ID_HEADER]
    for line in log_sink.lines(start):
        assert marker not in line


def test_auth_failure_and_validation_failure_are_logged_with_their_codes(client_factory, log_sink):
    anonymous = client_factory()
    start = len(log_sink.records)
    denied = anonymous.get("/api/v1/catalog")
    assert denied.status_code == 503
    denied_event = only_event(log_sink.events(start), "request.completed")
    assert denied_event["status"] == 503
    assert denied_event["error_code"] == "AUTH_NOT_CONFIGURED"
    assert denied_event["request_id"] == denied.headers[REQUEST_ID_HEADER]
    assert not any(event["event"] == "request.failed" for event in log_sink.events(start))

    user = client_factory(1)
    start = len(log_sink.records)
    invalid = user.post("/api/v1/catalog", json={"name": "", "owner_user_id": 2})
    assert invalid.status_code == 422
    invalid_event = only_event(log_sink.events(start), "request.completed")
    assert invalid_event["status"] == 422
    assert invalid_event["error_code"] == "VALIDATION_FAILED"
    assert invalid_event["request_id"] == invalid.headers[REQUEST_ID_HEADER]


def test_sequential_requests_keep_their_own_request_id(client_factory, log_sink):
    client = client_factory()
    observed = []
    for _ in range(3):
        start = len(log_sink.records)
        response = client.get("/health/live")
        completed = only_event(log_sink.events(start), "request.completed")
        observed.append((response.headers[REQUEST_ID_HEADER], completed["request_id"]))

    assert all(header == logged for header, logged in observed)
    assert len({header for header, _ in observed}) == 3

    start = len(log_sink.records)
    client.get("/health/live")
    client.put("/health/live")
    events = log_sink.events(start)
    completed = [event for event in events if event["event"] == "request.completed"]
    assert len(completed) == 2
    assert completed[0]["request_id"] != completed[1]["request_id"]
    assert completed[0]["error_code"] is None
    assert completed[1]["error_code"] == "METHOD_NOT_ALLOWED"


def test_parallel_requests_do_not_share_a_request_id(client_factory, log_sink):
    client = client_factory()
    start = len(log_sink.records)

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: client.get("/health/live"), range(8)))

    header_ids = [response.headers[REQUEST_ID_HEADER] for response in responses]
    assert len(header_ids) == 8
    assert len(set(header_ids)) == 8
    for response in responses:
        assert response.json()["status"] == "ok"

    completed = [
        event
        for event in log_sink.events(start)
        if event["event"] == "request.completed" and event["route"] == "/health/live"
    ]
    assert len(completed) == 8
    logged_ids = [event["request_id"] for event in completed]
    assert len(set(logged_ids)) == 8
    assert set(logged_ids) == set(header_ids)
    for event in completed:
        assert event["method"] == "GET"
        assert event["status"] == 200
        assert event["error_code"] is None


def test_log_lines_are_single_line_json_documents(client_factory, log_sink):
    client = client_factory()
    start = len(log_sink.records)
    client.get("/health/live")

    for line in log_sink.lines(start):
        assert "\n" not in line
        document = json.loads(line)
        assert {"ts", "level", "role", "event"} <= set(document)


def test_unhandled_exception_logs_type_only_and_no_exception_text(log_sink):
    app = create_app(Settings(environment="test", database_url="sqlite://", _env_file=None))

    @app.get("/boom")
    def boom():
        raise RuntimeError(
            "MARKER_EXCEPTION SELECT * FROM users password=hunter2 C:/secret/path.py"
        )

    with TestClient(app) as client:
        start = len(log_sink.records)
        response = client.get("/boom")

    assert response.status_code == 500
    events = log_sink.events(start)
    failed = only_event(events, "request.failed")
    completed = only_event(events, "request.completed")

    assert any(record.levelno == logging.ERROR for record in log_sink.records[start:])
    assert failed["level"] == "ERROR"
    assert failed["status"] == 500
    assert failed["code"] == "INTERNAL_ERROR"
    assert failed["category"] == "internal"
    assert failed["error_type"] == "RuntimeError"
    assert failed["route"] == "/boom"
    assert failed["request_id"] == response.headers[REQUEST_ID_HEADER]
    assert "fields" not in failed

    assert completed["status"] == 500
    assert completed["error_code"] == "INTERNAL_ERROR"
    assert completed["request_id"] == response.headers[REQUEST_ID_HEADER]
    assert isinstance(completed["duration_ms"], float)
    assert completed["duration_ms"] >= 0

    for line in log_sink.lines(start):
        for marker in (
            "MARKER_EXCEPTION",
            "SELECT * FROM",
            "hunter2",
            "C:/secret/path.py",
            "Traceback",
        ):
            assert marker not in line
        assert "<module>" not in line
        assert 'File "' not in line


def test_request_scope_correlates_events_and_is_cleared_afterwards(log_sink):
    start = len(log_sink.records)
    with request_scope("scope-request-id") as scoped:
        assert scoped == "scope-request-id"
        log_event("inside.scope")
    log_event("outside.scope")

    events = log_sink.events(start)
    inside = only_event(events, "inside.scope")
    outside = only_event(events, "outside.scope")
    assert inside["request_id"] == "scope-request-id"
    assert "request_id" not in outside


def test_request_scope_generates_an_id_when_none_is_given(log_sink):
    start = len(log_sink.records)
    with request_scope() as first, request_scope() as second:
        log_event("generated.scope")
    assert len(first) == 32
    assert first != second
    assert first == first.lower() and first.isalnum()
    event = only_event(log_sink.events(start), "generated.scope")
    assert event["request_id"] == second


def test_job_scope_adds_job_identity_to_events(log_sink):
    start = len(log_sink.records)
    with job_scope("job-1", "system.check", 2):
        log_event("job.claimed")
    log_event("job.outside")

    events = log_sink.events(start)
    inside = only_event(events, "job.claimed")
    outside = only_event(events, "job.outside")
    assert inside["job_id"] == "job-1"
    assert inside["job_type"] == "system.check"
    assert inside["attempt"] == 2
    assert "job_id" not in outside and "attempt" not in outside


def test_sensitive_keys_are_redacted_at_any_depth():
    redacted = sanitize(
        {
            "password": "hunter2",
            "user_password": "hunter2",
            "Authorization": "Bearer abc.def",
            "Cookie": "sid=abc",
            "access_token": "abc",
            "client_secret": "abc",
            "api_key": "abc",
            "lease_token": "abc",
            "database_url": "mysql://user:pw@db/market",
            "dsn": "postgresql://user:pw@db/market",
            "request_body": {"name": "visible-name"},
            "nested": {"password": "nested-secret", "keep": 1},
            "items": [{"token": "listed"}],
        }
    )
    for key in (
        "password",
        "user_password",
        "Authorization",
        "Cookie",
        "access_token",
        "client_secret",
        "api_key",
        "lease_token",
        "database_url",
        "dsn",
        "request_body",
    ):
        assert redacted[key] == REDACTED
    assert redacted["nested"] == {"password": REDACTED, "keep": 1}
    assert redacted["items"] == [{"token": REDACTED}]


def test_sanitize_value_renders_unknown_objects_as_class_names():
    class CredentialHolder:
        def __str__(self):
            return "password=hunter2"

    assert sanitize_value("value", CredentialHolder()) == "<CredentialHolder>"
    assert sanitize_value("value", b"12345") == "<5 bytes>"
    assert sanitize_value("value", bytearray(b"123")) == "<3 bytes>"
    assert sanitize_value("count", 3) == 3
    assert sanitize_value("ratio", 0.5) == 0.5
    assert sanitize_value("flag", True) is True
    assert sanitize_value("missing", None) is None
    assert sanitize_value("name", "plain text") == "plain text"


def test_sanitize_text_removes_credentials_from_free_form_strings():
    assert REDACTED_URL in sanitize_text("mysql+pymysql://root:s3cret@db:3306/market")
    assert REDACTED_URL in sanitize_text("postgresql://user:pw@example.com/market")
    assert REDACTED_URL in sanitize_text("https://alice:tok3n@example.com/private")
    assert sanitize_text("connect password=hunter2 retry=3") == (
        f"connect password={REDACTED} retry=3"
    )
    assert sanitize_text("token: abc123") == f"token={REDACTED}"
    assert sanitize_text("Bearer abc123") == f"Bearer {REDACTED}"
    assert sanitize_text("Basic dXNlcjpwYXNz") == f"Basic {REDACTED}"
    assert "hunter2" not in sanitize_text("password=hunter2")
    assert "s3cret" not in sanitize_text("mysql://root:s3cret@db/market")
    assert "tok3n" not in sanitize_text("https://alice:tok3n@example.com/private")
    assert sanitize_text("just a normal message") == "just a normal message"
    assert sanitize_text("see https://example.com/docs") == "see https://example.com/docs"

    bounded = sanitize_text("x" * (MAX_TEXT + 100))
    assert len(bounded) == MAX_TEXT + 1
    assert bounded.endswith("…")


def test_safe_headers_is_an_allow_list():
    headers = safe_headers(
        {
            "Authorization": "Bearer abc123",
            "Cookie": "sid=abc123",
            "X-Api-Key": "abc123",
            "Content-Type": "application/json",
            "User-Agent": "pytest",
            "X-Request-ID": "request-id-1",
        }
    )
    assert headers == {
        "content-type": "application/json",
        "user-agent": "pytest",
        "x-request-id": "request-id-1",
    }
    assert "Bearer abc123" not in json.dumps(headers)
    assert "sid=abc123" not in json.dumps(headers)


def test_error_fields_reports_only_the_exception_class():
    assert error_fields(RuntimeError("SELECT * FROM users password=hunter2")) == {
        "error_type": "RuntimeError"
    }
    assert error_fields(ValueError("C:/secret/path.py")) == {"error_type": "ValueError"}

    error = KeyError("password=hunter2")
    fields = error_fields(error)
    assert fields == {"error_type": "KeyError"}
    rendered = json.dumps(fields)
    assert "hunter2" not in rendered
    assert "C:/secret/path.py" not in rendered


def test_authorization_header_text_does_not_keep_the_credential():
    """Free text must lose the credential after a Bearer/Basic scheme keyword."""
    for text in (
        "Authorization: Bearer abc123",
        "authorization: bearer SECRET998877",
        "Authorization: Basic dXNlcjpwYXNz",
    ):
        cleaned = sanitize_text(text)
        assert "abc123" not in cleaned
        assert "SECRET998877" not in cleaned
        assert "dXNlcjpwYXNz" not in cleaned


def test_log_event_redacts_before_serializing(log_sink):
    start = len(log_sink.records)
    log_event(
        "redaction.probe",
        password="hunter2",
        token="token-value",
        Authorization="Bearer bearer-value",
        Cookie="sid=cookie-value",
        database_url="mysql+pymysql://root:dsn-password@db:3306/market",
        note="https://alice:url-password@example.com/private",
        request_payload={"password": "nested-password"},
        count=2,
    )
    line = log_sink.lines(start)[-1]
    document = json.loads(line)

    assert document["event"] == "redaction.probe"
    assert document["password"] == REDACTED
    assert document["token"] == REDACTED
    assert document["Authorization"] == REDACTED
    assert document["Cookie"] == REDACTED
    assert document["database_url"] == REDACTED
    assert document["note"] == REDACTED_URL
    assert document["request_payload"] == REDACTED
    assert document["count"] == 2
    for secret in ("hunter2", "token-value", "bearer-value", "cookie-value", "dsn-password"):
        assert secret not in line
    assert "url-password" not in line
    assert "nested-password" not in line


def test_log_event_is_suppressed_below_the_configured_level(log_sink):
    logger = logging.getLogger(EVENT_LOGGER)
    start = len(log_sink.records)
    try:
        logger.setLevel(logging.INFO)
        log_event("debug.only", level=logging.DEBUG)
        log_event("info.event")
    finally:
        logger.setLevel(logging.DEBUG)

    events = [event["event"] for event in log_sink.events(start)]
    assert "debug.only" not in events
    assert "info.event" in events


def test_json_formatter_passes_our_events_through_and_wraps_foreign_records(log_sink):
    from research_platform.core.logging import JsonFormatter

    start = len(log_sink.records)
    log_event("formatter.own", request_id_extra="value")
    own = log_sink.records[start]
    assert json.loads(own.getMessage())["event"] == "formatter.own"

    foreign = logging.LogRecord(
        name="some_library",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="failed with password=hunter2",
        args=(),
        exc_info=None,
    )
    rendered = JsonFormatter().format(foreign)
    document = json.loads(rendered)
    assert document["event"] == "library"
    assert document["logger"] == "some_library"
    assert document["level"] == "WARNING"
    assert "hunter2" not in rendered
