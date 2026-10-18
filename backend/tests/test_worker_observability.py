"""Worker observability, failure classification and bounded connection retry.

Events are captured as their parsed JSON documents because that line is what an
operator and the log shipper actually see. Job state assertions go through the
real execution service, so a worker that writes a different terminal state fails
the test instead of only mismatching a log string.
"""

import json
import logging
import signal
import threading
from contextlib import contextmanager
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from research_platform.core.database import make_engine
from research_platform.core.logging import ROLE_WORKER, current_job_id
from research_platform.modules.execution import worker
from research_platform.modules.execution.models import Job, utc_now
from research_platform.modules.execution.schemas import JobCreate
from research_platform.modules.execution.service import claim_job, submit_job
from research_platform.modules.execution.worker import run_once

LOGGER = "research_platform"
SENSITIVE_MARKERS = (
    "lease_token",
    "hunter2",
    "db.internal",
    "mysql://",
    "Traceback",
    "connection refused",
)


class EventCollector(logging.Handler):
    """Store each structured event as the parsed JSON document it emitted."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.events: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(record, "event", None):
            self.events.append(json.loads(record.getMessage()))

    def named(self, event: str) -> list[dict]:
        return [item for item in self.events if item["event"] == event]

    def single(self, event: str) -> dict:
        matches = self.named(event)
        assert len(matches) == 1, (event, matches)
        return matches[0]

    def render(self) -> str:
        return json.dumps(self.events, ensure_ascii=False)


@pytest.fixture
def events():
    collector = EventCollector()
    logger = logging.getLogger(LOGGER)
    previous_level = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(collector)
    try:
        yield collector
    finally:
        logger.removeHandler(collector)
        logger.setLevel(previous_level)


@pytest.fixture
def engine(database_url):
    engine = make_engine(database_url)
    try:
        yield engine
    finally:
        engine.dispose()


def enqueue(session: Session) -> Job:
    return submit_job(
        session, 1, JobCreate(job_type="system.check", idempotency_key="worker-key-1")
    )


@contextmanager
def _no_session(_engine):
    """Stand-in for ``Session(engine)`` in loop tests that never touch the DB."""
    yield None


class _DummyEngine:
    disposed = False

    def dispose(self) -> None:
        self.disposed = True


class _RecordingStopEvent(threading.Event):
    """Records requested waits; by default never stops and never really blocks."""

    def __init__(self, stop_when: bool = False) -> None:
        super().__init__()
        self.waits: list[float | None] = []
        self.stop_when = stop_when

    def wait(self, timeout=None):  # noqa: ANN001 - mirrors threading.Event
        self.waits.append(timeout)
        return self.stop_when


def test_successful_job_events_carry_job_correlation(events, session):
    job = enqueue(session)

    assert run_once(session) is True

    claimed = events.single("job.claimed")
    completed = events.single("job.completed")
    for event in (claimed, completed):
        assert event["job_id"] == job.id
        assert event["job_type"] == "system.check"
        assert event["attempt"] == 1
    assert completed["outcome"] == "succeeded"
    assert completed["error_code"] is None
    assert isinstance(completed["duration_ms"], float)
    # The lease token is a bearer credential and must never enter the log.
    assert "lease_token" not in events.render()
    # Context is scoped to the job and released once the task finishes.
    assert current_job_id() is None


def test_diagnostic_failure_is_classified_without_leaking_the_exception(
    events, session, monkeypatch
):
    job = enqueue(session)

    def explode(_sql):
        raise RuntimeError("password=hunter2 host=db.internal")

    # Only the worker's own probe is broken; claim and finish still work.
    monkeypatch.setattr(worker, "text", explode)

    assert run_once(session) is True

    completed = events.single("job.completed")
    assert completed["outcome"] == "failed"
    assert completed["error_code"] == "DIAGNOSTIC_FAILED"
    assert completed["error_type"] == "RuntimeError"
    rendered = events.render()
    for marker in SENSITIVE_MARKERS:
        assert marker not in rendered
    row = session.get(Job, job.id, populate_existing=True)
    assert row.state == "FAILED"
    assert row.error_code == "DIAGNOSTIC_FAILED"


def test_unregistered_handler_fails_with_controlled_code(events, session):
    job = enqueue(session)
    job.job_type = "unregistered.research"
    session.commit()

    assert run_once(session) is True

    completed = events.single("job.completed")
    assert completed["outcome"] == "failed"
    assert completed["error_code"] == "HANDLER_NOT_REGISTERED"
    assert session.get(Job, job.id, populate_existing=True).error_code == "HANDLER_NOT_REGISTERED"


def test_attempt_number_is_correlated_after_lease_expiry(events, session):
    job = enqueue(session)
    # A lease that already expired lets the worker claim the same job again.
    first = claim_job(session, utc_now() - timedelta(seconds=70))
    assert first is not None and first.job_id == job.id

    assert run_once(session) is True

    assert events.single("job.claimed")["attempt"] == 2
    assert events.single("job.completed")["attempt"] == 2


def test_rejected_terminal_state_is_reported_as_lease_rejected(events, session, monkeypatch):
    enqueue(session)

    def reject(_session, _lease, _result, _error=None):
        return False

    monkeypatch.setattr(worker, "finish_job", reject)

    assert run_once(session) is True

    completed = events.single("job.completed")
    assert completed["outcome"] == "rejected"
    assert completed["error_code"] == "LEASE_REJECTED"


def test_idle_wait_uses_the_stop_event_instead_of_sleep(events, monkeypatch):
    monkeypatch.setattr(worker, "Session", _no_session)
    monkeypatch.setattr(worker, "run_once", lambda _session: False)
    sleeps: list[float] = []
    monkeypatch.setattr("time.sleep", lambda seconds: sleeps.append(seconds))
    stop_event = _RecordingStopEvent(stop_when=True)

    assert worker.run_worker(_DummyEngine(), stop_event=stop_event, poll_seconds=3.5) == 0
    assert stop_event.waits == [3.5]
    assert sleeps == []


def test_connect_retry_is_bounded_and_resets_after_recovery(events, monkeypatch):
    monkeypatch.setattr(worker, "Session", _no_session)
    script = ["fail", "fail", "ok", "fail", "fail", "fail", "fail"]

    def flaky(_session):
        if script.pop(0) == "fail":
            raise SQLAlchemyError("connection refused to mysql://user:secret@db/app")
        return True

    monkeypatch.setattr(worker, "run_once", flaky)
    stop_event = _RecordingStopEvent()

    assert worker.run_worker(_DummyEngine(), stop_event=stop_event) == 1

    # 1/2/4 seconds come from the reviewed WORKER_CONNECT policy; the counter
    # resets after the successful pass, so the budget is consecutive failures.
    assert stop_event.waits == [1.0, 2.0, 1.0, 2.0, 4.0]
    assert len(events.named("worker.connect_retry")) == 5
    retry = events.named("worker.connect_retry")[0]
    assert retry["error_code"] == "DATABASE_UNAVAILABLE"
    assert retry["retry"] == 1
    assert retry["max_retries"] == 3
    assert retry["error_type"] == "SQLAlchemyError"
    fatal = events.single("worker.fatal")
    assert fatal["error_code"] == "DATABASE_UNAVAILABLE"
    rendered = events.render()
    for marker in SENSITIVE_MARKERS:
        assert marker not in rendered


def test_stop_during_connect_backoff_returns_cleanly(events, monkeypatch):
    monkeypatch.setattr(worker, "Session", _no_session)

    def always_fail(_session):
        raise SQLAlchemyError("connection refused")

    monkeypatch.setattr(worker, "run_once", always_fail)
    stop_event = _RecordingStopEvent(stop_when=True)

    assert worker.run_worker(_DummyEngine(), stop_event=stop_event) == 0
    assert events.named("worker.connect_retry")
    assert not events.named("worker.fatal")


def test_stop_event_is_honoured_before_claiming_more_work(events, monkeypatch):
    monkeypatch.setattr(worker, "Session", _no_session)
    claimed: list[bool] = []

    def should_not_run(_session):
        claimed.append(True)
        return True

    monkeypatch.setattr(worker, "run_once", should_not_run)
    stop_event = _RecordingStopEvent()
    stop_event.set()

    assert worker.run_worker(_DummyEngine(), stop_event=stop_event) == 0
    assert claimed == []


def test_stop_signals_cover_interrupt_and_termination(events):
    assert signal.SIGINT in worker.STOP_SIGNALS
    assert signal.SIGTERM in worker.STOP_SIGNALS
    # Windows console CTRL_BREAK raises SIGBREAK; without it the process would
    # die abruptly instead of finishing its current task at a boundary.
    if hasattr(signal, "SIGBREAK"):
        assert signal.SIGBREAK in worker.STOP_SIGNALS
    assert len(set(worker.STOP_SIGNALS)) == len(worker.STOP_SIGNALS)


def test_run_worker_once_processes_a_real_job(events, engine, session):
    job = enqueue(session)
    session.commit()

    assert worker.run_worker(engine, once=True) == 0

    events.single("job.claimed")
    completed = events.single("job.completed")
    assert completed["outcome"] == "succeeded"
    assert completed["job_id"] == job.id
    row = session.get(Job, job.id, populate_existing=True)
    assert row.state == "SUCCEEDED"
    assert row.result == {"database": "reachable"}


def test_main_configures_worker_logging_and_restores_stop_handlers(events, monkeypatch):
    calls: dict[str, Any] = {}

    class FakeSettings:
        environment = "test"
        log_level = "DEBUG"

        def require_development_release(self) -> None:
            calls["released"] = True

    def fake_configure_logging(role, level):
        calls["logging"] = (role, level)

    def fake_run_worker(_engine, *, once=False, stop_event=None, poll_seconds=None):
        calls["run"] = {"once": once, "stop_event": stop_event, "poll_seconds": poll_seconds}
        return 0

    original_sigterm = signal.getsignal(signal.SIGTERM)

    monkeypatch.setattr(worker, "Settings", lambda: FakeSettings())
    monkeypatch.setattr(worker, "make_application_engine", lambda _settings: _DummyEngine())
    monkeypatch.setattr(worker, "configure_logging", fake_configure_logging)
    monkeypatch.setattr(worker, "run_worker", fake_run_worker)

    assert worker.main(["--once"]) is None

    assert calls["released"] is True
    assert calls["logging"] == (ROLE_WORKER, "DEBUG")
    assert calls["run"]["once"] is True
    assert isinstance(calls["run"]["stop_event"], threading.Event)
    started = events.single("worker.started")
    assert started["environment"] == "test"
    assert started["poll_seconds"] == worker.POLL_SECONDS
    assert started["connect_retry_delays"] == [1.0, 2.0, 4.0]
    assert events.single("worker.stopped")["exit_code"] == 0
    # main() must not leave its handler behind for the next embedder.
    assert signal.getsignal(signal.SIGTERM) == original_sigterm


def test_main_treats_keyboard_interrupt_as_a_clean_stop(events, monkeypatch):
    class FakeSettings:
        environment = "test"
        log_level = "INFO"

        def require_development_release(self) -> None:
            return None

    def interrupted(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(worker, "Settings", lambda: FakeSettings())
    monkeypatch.setattr(worker, "make_application_engine", lambda _settings: _DummyEngine())
    monkeypatch.setattr(worker, "configure_logging", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker, "run_worker", interrupted)

    # Ctrl+C is a requested stop, so main() returns without SystemExit and still
    # disposes the engine and records the stop event.
    assert worker.main([]) is None
    assert events.single("worker.stopped")["exit_code"] == 0


def test_main_exits_non_zero_after_the_retry_budget_is_exhausted(events, monkeypatch):
    class FakeSettings:
        environment = "test"
        log_level = "INFO"

        def require_development_release(self) -> None:
            return None

    monkeypatch.setattr(worker, "Settings", lambda: FakeSettings())
    monkeypatch.setattr(worker, "make_application_engine", lambda _settings: _DummyEngine())
    monkeypatch.setattr(worker, "configure_logging", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker, "run_worker", lambda *args, **kwargs: 1)

    with pytest.raises(SystemExit) as exited:
        worker.main([])

    assert exited.value.code == 1
    assert events.single("worker.stopped")["exit_code"] == 1
