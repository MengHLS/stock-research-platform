"""Structured logging, correlation context and redaction.

One JSON line per event on stdout; rotation and shipping belong to the runtime.
Everything that may contain a credential is filtered here, before serialization,
so a log call can never leak a password, session token or connection string.

Correlation (see docs/architecture.md "统一错误与日志"):

- every HTTP request gets a server-generated id, exposed as ``X-Request-ID`` and
  repeated in the error body; log lines inside the request carry the same value;
- every job event carries ``job_id`` plus ``attempt``; the lease token is never
  logged because it is a bearer credential for the job.
"""

import json
import logging
import re
import sys
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

EVENT_LOGGER = "research_platform"

ROLE_API = "api"
ROLE_WORKER = "worker"

_role = ROLE_API

# Context is per task/thread so concurrent requests cannot borrow each other's
# identifiers. Reset in a finally block; never persist context across requests.
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_job_id: ContextVar[str | None] = ContextVar("job_id", default=None)
_job_type: ContextVar[str | None] = ContextVar("job_type", default=None)
_attempt: ContextVar[int | None] = ContextVar("attempt", default=None)

# Field names whose values are never safe to serialize. Matching is by
# substring on the lowered key so ``user_password`` and ``Authorization`` are
# covered without enumerating every spelling.
_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "auth",
    "cookie",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "credential",
    "session",
    "dsn",
    "connection",
    "lease",
    "database_url",
    "url",
    "body",
    "payload",
)

REDACTED = "[redacted]"
REDACTED_URL = "[redacted-url]"
MAX_TEXT = 200

# Absolute location of a URL with embedded userinfo or a database DSN.
_URL_WITH_CREDENTIALS = re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.-]*://[^\s/@:]+:[^\s/@]*@[^\s]*")
# ``password=hunter2`` / ``token: abc`` style assignments. The key may carry a
# prefix (``access_token``, ``x-api-key``); the lookbehind accepts that separator
# while still refusing to match inside a longer word. A value that is itself a
# scheme keyword (``Authorization: Bearer``) is left for _BEARER below, so the
# credential after the keyword is replaced instead of the keyword itself.
_ASSIGNED_SECRET = re.compile(
    r"(?i)(?<![a-z0-9])"
    r"((?:[a-z0-9]+[_-])?(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|"
    r"authorization|cookie|session[_-]?id))"
    r"\s*[=:]\s*(?!bearer\b|basic\b)[^\s,;&]+"
)
# ``Bearer <token>`` / ``Basic <base64>`` anywhere in free text. Run before the
# assignment rule so ``Authorization: Bearer abc`` cannot be half-consumed.
_BEARER = re.compile(r"(?i)\b(bearer|basic)\s+(?!\[redacted\])[A-Za-z0-9._~+/=-]+")
# A whole DSN, which may or may not carry userinfo.
_URL_SCHEME = re.compile(r"\b(mysql|mysql\+pymysql|postgresql|postgres|redis|mongodb|oracle)://\S+")


def utc_iso() -> str:
    """ISO 8601 UTC with a ``Z`` suffix; log timestamps are not local time."""
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_request_id() -> str:
    return uuid.uuid4().hex


def current_request_id() -> str | None:
    return _request_id.get()


def current_job_id() -> str | None:
    return _job_id.get()


def context_fields() -> dict[str, Any]:
    """Correlation fields for the active scope, omitting absent values."""
    fields: dict[str, Any] = {}
    for key, value in (
        ("request_id", _request_id.get()),
        ("job_id", _job_id.get()),
        ("job_type", _job_type.get()),
        ("attempt", _attempt.get()),
    ):
        if value is not None:
            fields[key] = value
    return fields


class _ContextToken:
    """Opaque handle used to restore the previous context in ``finally``."""

    __slots__ = ("tokens",)

    def __init__(self, tokens: tuple) -> None:
        self.tokens = tokens


@contextmanager
def request_scope(request_id: str | None = None) -> Iterator[str]:
    """Attach a request id to every log event emitted inside the block."""
    value = request_id or new_request_id()
    token = _request_id.set(value)
    try:
        yield value
    finally:
        _request_id.reset(token)


@contextmanager
def job_scope(job_id: str, job_type: str, attempt: int) -> Iterator[None]:
    """Attach job identifiers to worker events; the lease token is never passed."""
    tokens = (_job_id.set(job_id), _job_type.set(job_type), _attempt.set(attempt))
    try:
        yield
    finally:
        _job_id.reset(tokens[0])
        _job_type.reset(tokens[1])
        _attempt.reset(tokens[2])


def _sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def sanitize_text(value: str) -> str:
    """Strip credentials from one free-form string and bound its length."""
    cleaned = _URL_WITH_CREDENTIALS.sub(REDACTED_URL, value)
    cleaned = _URL_SCHEME.sub(REDACTED_URL, cleaned)
    # Scheme keyword first: ``Authorization: Bearer abc`` must lose ``abc`` even
    # though the assignment rule would match the ``Authorization`` keyword.
    cleaned = _BEARER.sub(lambda match: f"{match.group(1)} {REDACTED}", cleaned)
    cleaned = _ASSIGNED_SECRET.sub(lambda match: f"{match.group(1)}={REDACTED}", cleaned)
    if len(cleaned) > MAX_TEXT:
        cleaned = f"{cleaned[:MAX_TEXT]}…"
    return cleaned


def sanitize_value(key: str, value: Any) -> Any:
    """Recursively redact sensitive keys and credential-shaped values."""
    if _sensitive_key(key):
        return REDACTED
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, Mapping):
        return {str(k): sanitize_value(str(k), v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_value(key, item) for item in value]
    if isinstance(value, (bytes, bytearray)):
        return f"<{len(value)} bytes>"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    # Arbitrary objects may render credentials in __str__/__repr__.
    return f"<{type(value).__name__}>"


def sanitize(fields: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): sanitize_value(str(key), value) for key, value in fields.items()}


def safe_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Allow-list request headers; credentials and cookies never reach the log."""
    allowed = {
        "content-type",
        "content-length",
        "accept",
        "user-agent",
        "x-request-id",
        "origin",
        "referer",
    }
    return {
        key.lower(): sanitize_text(str(value))
        for key, value in headers.items()
        if key.lower() in allowed
    }


def error_fields(exception: BaseException) -> dict[str, Any]:
    """Log the exception class only: messages and tracebacks may carry secrets."""
    return {"error_type": type(exception).__name__}


def _payload(event: str, level: str, fields: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ts": utc_iso(),
        "level": level,
        "role": _role,
        "event": event,
    }
    payload.update(context_fields())
    payload.update(sanitize(fields))
    return payload


def log_event(event: str, *, level: int = logging.INFO, **fields: Any) -> None:
    """Emit one structured event. Fields are redacted and context is merged."""
    logger = logging.getLogger(EVENT_LOGGER)
    if not logger.isEnabledFor(level):
        return
    # The rendered message is the JSON document itself so that both the stdout
    # handler and a test handler observe exactly the same, already-safe record.
    message = json.dumps(
        _payload(event, logging.getLevelName(level), fields),
        ensure_ascii=False,
        default=str,
    )
    logger.log(level, message, extra={"event": event, "data": sanitize(fields)})


class JsonFormatter(logging.Formatter):
    """Keep our own events as-is; wrap third-party records in the same shape."""

    def format(self, record: logging.LogRecord) -> str:
        if getattr(record, "event", None):
            return record.getMessage()
        return json.dumps(
            {
                "ts": utc_iso(),
                "level": record.levelname,
                "role": _role,
                "event": "library",
                "logger": record.name,
                "message": sanitize_text(record.getMessage()),
            },
            ensure_ascii=False,
        )


def configure_logging(role: str = ROLE_API, level: str = "INFO") -> None:
    """Configure one JSON stream handler. Safe to call more than once."""
    global _role
    _role = role
    numeric = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(numeric)
    for handler in list(root.handlers):
        if getattr(handler, "_research_platform", False):
            root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler._research_platform = True  # type: ignore[attr-defined]
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    # Uvicorn installs its own colourised handlers; route it through the JSON one
    # so a deployment has a single log format.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        library = logging.getLogger(name)
        library.handlers = []
        library.propagate = True
        library.setLevel(numeric)
