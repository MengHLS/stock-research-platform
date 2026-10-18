"""Timeout and retry rules, declared once and applied per access type.

The shape of the rule is shared; the numbers are not. A rule that retries a
write is dangerous, a rule that retries a read is merely wasteful, and a
diagnostic probe must fail fast instead of holding a page open. See
docs/architecture.md "超时与重试" for the reviewed table.

``kind`` is the access type, not the transport. The same HTTP client, database
session or job claim can therefore be tuned without copying magic numbers into
call sites; every place that waits on I/O imports the policy instead.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AccessPolicy:
    """One reviewed timing rule for one kind of access."""

    kind: str
    timeout_seconds: float
    max_retries: int
    backoff_seconds: tuple[float, ...]
    retryable_statuses: tuple[int, ...] = ()
    note: str = ""

    def retry_delay(self, attempt: int) -> float | None:
        """Delay before retry ``attempt`` (1-based); ``None`` means stop."""
        if attempt < 1 or attempt > self.max_retries:
            return None
        if not self.backoff_seconds:
            return 0.0
        index = min(attempt - 1, len(self.backoff_seconds) - 1)
        return self.backoff_seconds[index]


# Read: safe to repeat, so exactly one bounded retry. Only transient loss of
# the peer is retried; validation, auth and rate limiting are not.
READ = AccessPolicy(
    kind="read",
    timeout_seconds=15.0,
    max_retries=1,
    backoff_seconds=(0.3,),
    retryable_statuses=(502, 503, 504),
    note="GET/HEAD only; one retry, then surface the failure.",
)

# Write: never retried automatically. A write may have been committed before the
# response was lost, and idempotency must come from the existing job/unique-key
# constraint, not from a hidden second request.
WRITE = AccessPolicy(
    kind="write",
    timeout_seconds=30.0,
    max_retries=0,
    backoff_seconds=(),
    note="POST/PUT/PATCH/DELETE; duplicate protection belongs to idempotency keys.",
)

# Diagnostic: health probes must answer quickly and must not multiply load.
DIAGNOSTIC = AccessPolicy(
    kind="diagnostic",
    timeout_seconds=5.0,
    max_retries=0,
    backoff_seconds=(),
    note="liveness/readiness; fail fast, no retry.",
)

# Worker connection: bounded process-level retry with 1/2/4 second backoff.
# This counts process recovery, never a new research attempt.
WORKER_CONNECT = AccessPolicy(
    kind="worker-connect",
    timeout_seconds=10.0,
    max_retries=3,
    backoff_seconds=(1.0, 2.0, 4.0),
    note="temporary database loss in the worker process; resets after recovery.",
)

# Database read: the server-side read timeout is configured on the connection
# (MySQLConfig.read_timeout). This entry documents the expected ceiling so a
# migration or report query does not silently raise it.
DATABASE_READ = AccessPolicy(
    kind="database-read",
    timeout_seconds=60.0,
    max_retries=0,
    backoff_seconds=(),
    note="read_timeout on the connection; retries are decided by the caller.",
)

POLICIES: dict[str, AccessPolicy] = {
    policy.kind: policy for policy in (READ, WRITE, DIAGNOSTIC, WORKER_CONNECT, DATABASE_READ)
}


def policy_for(kind: str) -> AccessPolicy:
    try:
        return POLICIES[kind]
    except KeyError:
        raise KeyError(f"Unknown access policy kind: {kind}") from None
