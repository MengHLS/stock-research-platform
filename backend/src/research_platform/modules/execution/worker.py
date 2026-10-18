import argparse
import logging
import signal
import sys
import threading
import time
from collections.abc import Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from research_platform.core.config import Settings
from research_platform.core.database import make_application_engine
from research_platform.core.logging import (
    ROLE_WORKER,
    configure_logging,
    error_fields,
    job_scope,
    log_event,
)
from research_platform.core.policies import WORKER_CONNECT

from .models import Job
from .service import claim_job, finish_job

# Idle polling interval. Waiting on it must stay interruptible by the stop signal.
POLL_SECONDS = 2.0

# Process-level recovery, never a new research attempt: the numbers come from the
# reviewed WORKER_CONNECT policy instead of a second copy of 1/2/4 seconds.
RETRY_DELAYS: tuple[float, ...] = WORKER_CONNECT.backoff_seconds

# SIGINT/SIGTERM everywhere, plus SIGBREAK where it exists (Windows console
# CTRL_BREAK). All of them only flip the stop event; the loop exits at a
# boundary instead of dying mid-task.
STOP_SIGNALS: tuple[int, ...] = tuple(
    signum
    for signum in (signal.SIGINT, signal.SIGTERM, getattr(signal, "SIGBREAK", None))
    if signum is not None
)


def _attempt_of(session: Session, job_id: str) -> int:
    """``claim_job`` already incremented attempts; read it back for correlation."""
    job = session.get(Job, job_id)
    return job.attempts if job is not None else 1


def run_once(session: Session) -> bool:
    lease = claim_job(session)
    if lease is None:
        return False
    started = time.perf_counter()
    with job_scope(lease.job_id, lease.job_type, _attempt_of(session, lease.job_id)):
        log_event("job.claimed")
        failure: BaseException | None = None
        error_code: str | None = None
        # Only a bounded infrastructure diagnostic is registered in the starter.
        # Real research needs heartbeat/cancellation/Run integration before registration.
        if lease.job_type == "system.check":
            try:
                session.execute(text("SELECT 1"))
                accepted = finish_job(session, lease, {"database": "reachable"})
            except Exception as exc:
                # The message and traceback can carry SQL or credentials, so the
                # completion event records a controlled code and the type only.
                failure = exc
                session.rollback()
                error_code = "DIAGNOSTIC_FAILED"
                accepted = finish_job(session, lease, None, error_code)
        else:
            error_code = "HANDLER_NOT_REGISTERED"
            accepted = finish_job(session, lease, None, error_code)
        if not accepted:
            # The lease expired or moved on: the terminal state was not accepted.
            outcome, error_code = "rejected", "LEASE_REJECTED"
        elif error_code is None:
            outcome = "succeeded"
        else:
            outcome = "failed"
        fields: dict[str, Any] = {
            "outcome": outcome,
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            "error_code": error_code,
        }
        if failure is not None:
            fields.update(error_fields(failure))
        log_event("job.completed", **fields)
    return True


def _install_stop_handlers(stop_event: threading.Event) -> dict[int, Any]:
    """SIGINT/SIGTERM/SIGBREAK only set the event so the loop can finish cleanly."""

    def request_stop(_signum: int, _frame: Any) -> None:
        stop_event.set()

    previous: dict[int, Any] = {}
    for signum in STOP_SIGNALS:
        try:
            previous[signum] = signal.signal(signum, request_stop)
        except (OSError, ValueError):
            # Only the main thread may install handlers; the loop still honours
            # KeyboardInterrupt and a caller can set the event directly.
            continue
    return previous


def _restore_stop_handlers(previous: dict[int, Any]) -> None:
    for signum, handler in previous.items():
        try:
            signal.signal(signum, handler)
        except (OSError, ValueError):
            continue


def run_worker(
    engine: Engine,
    *,
    once: bool = False,
    stop_event: threading.Event | None = None,
    poll_seconds: float = POLL_SECONDS,
) -> int:
    """Claim and finish jobs until a stop signal arrives; returns the process code."""
    stop_event = stop_event or threading.Event()
    failures = 0
    while not stop_event.is_set():
        try:
            with Session(engine) as session:
                did_work = run_once(session)
        except SQLAlchemyError as exc:
            # Temporary database loss is a process-level failure; the job attempt
            # and its lease stay with the queue rules, not with this retry count.
            if failures >= len(RETRY_DELAYS):
                log_event(
                    "worker.fatal",
                    level=logging.ERROR,
                    error_code="DATABASE_UNAVAILABLE",
                    retries=failures,
                    **error_fields(exc),
                )
                return 1
            delay = RETRY_DELAYS[failures]
            failures += 1
            log_event(
                "worker.connect_retry",
                level=logging.WARNING,
                error_code="DATABASE_UNAVAILABLE",
                retry=failures,
                max_retries=len(RETRY_DELAYS),
                delay_seconds=delay,
                **error_fields(exc),
            )
            if stop_event.wait(delay):
                return 0
            continue
        # A completed pass proves the connection works again; reset the budget.
        failures = 0
        if once:
            return 0
        # Idle waiting must be interruptible: time.sleep would keep a stopped
        # worker alive for the whole poll interval.
        if not did_work and stop_event.wait(poll_seconds):
            return 0
    return 0


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the bounded diagnostic worker")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    settings = Settings()
    configure_logging(role=ROLE_WORKER, level=settings.log_level)
    settings.require_development_release()
    engine = make_application_engine(settings)
    stop_event = threading.Event()
    previous_handlers = _install_stop_handlers(stop_event)
    exit_code = 0
    log_event(
        "worker.started",
        environment=settings.environment,
        poll_seconds=POLL_SECONDS,
        connect_retry_delays=list(RETRY_DELAYS),
    )
    try:
        exit_code = run_worker(engine, once=args.once, stop_event=stop_event)
    except KeyboardInterrupt:
        # Ctrl+C is a requested stop, not a crash; the finally block still runs.
        exit_code = 0
    finally:
        _restore_stop_handlers(previous_handlers)
        engine.dispose()
        log_event("worker.stopped", exit_code=exit_code)
    if exit_code:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
