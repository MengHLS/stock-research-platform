"""The timeout/retry table exists twice; this test keeps the two copies equal.

The backend owns `core/policies.py` (worker connection, database reads) and the
frontend owns `frontend/src/api/policies.ts` (read/write/diagnostic HTTP). They
cannot import each other, so the only protection against silent divergence is a
literal comparison here. If a number changes, change both sides and this table.
"""

import re
from pathlib import Path

from research_platform.core.policies import (
    DATABASE_READ,
    DIAGNOSTIC,
    READ,
    WORKER_CONNECT,
    WRITE,
    policy_for,
)

FRONTEND_API = Path(__file__).resolve().parents[2] / "frontend/src/api"


def _frontend_source() -> str:
    return (FRONTEND_API / "policies.ts").read_text(encoding="utf-8")


def test_http_access_types_use_the_same_numbers_on_both_sides():
    source = _frontend_source()
    errors = (FRONTEND_API / "errors.ts").read_text(encoding="utf-8")
    assert "DEFAULT_TIMEOUT_MS = 15_000" in source
    assert "WRITE_TIMEOUT_MS = 30_000" in source
    assert "DIAGNOSTIC_TIMEOUT_MS = 5_000" in source
    assert "READ_RETRY_DELAY_MS = 300" in source
    assert "RETRYABLE_STATUSES: readonly number[] = [502, 503, 504]" in errors

    assert READ.timeout_seconds == 15.0
    assert READ.max_retries == 1
    assert READ.backoff_seconds == (0.3,)
    assert WRITE.timeout_seconds == 30.0
    assert WRITE.max_retries == 0
    assert DIAGNOSTIC.timeout_seconds == 5.0
    assert DIAGNOSTIC.max_retries == 0


def test_frontend_declares_no_retry_for_write_or_diagnostic():
    source = _frontend_source()
    write_block = source.split("export const WRITE_POLICY", 1)[1].split("}", 1)[0]
    diagnostic_block = source.split("export const DIAGNOSTIC_POLICY", 1)[1].split("}", 1)[0]
    assert "maxRetries: 0" in write_block
    assert "maxRetries: 0" in diagnostic_block


def test_only_read_retries_and_only_on_transient_statuses():
    # Guards the invariant that matters: a retryable write would be a data bug.
    for policy in (WRITE, DIAGNOSTIC, DATABASE_READ):
        assert policy.max_retries == 0, policy.kind
    assert READ.retryable_statuses == (502, 503, 504)
    assert 429 not in READ.retryable_statuses
    assert 500 not in READ.retryable_statuses
    assert WORKER_CONNECT.backoff_seconds == (1.0, 2.0, 4.0)
    assert WORKER_CONNECT.max_retries == 3


def test_policy_lookup_covers_and_rejects():
    for kind in ("read", "write", "diagnostic", "worker-connect", "database-read"):
        assert policy_for(kind).kind == kind
    try:
        policy_for("submit")
    except KeyError:
        pass
    else:  # pragma: no cover - failing path is the assertion
        raise AssertionError("submit has no implemented access path")


def test_documented_table_lists_every_implemented_access_type():
    architecture = (Path(__file__).resolve().parents[2] / "docs/architecture.md").read_text(
        encoding="utf-8"
    )
    table = architecture.split("| 访问类型 | 适用 | 超时 | 自动重试 |", 1)[1].split("\n\n", 1)[0]
    rows = {match.group(1) for match in re.finditer(r"^\| ([a-z-]+) \|", table, re.MULTILINE)}
    assert rows == {"read", "write", "diagnostic", "worker-connect", "database-read"}
