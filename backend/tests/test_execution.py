from datetime import timedelta

from sqlalchemy.orm import Session

from research_platform.core.database import make_engine
from research_platform.modules.execution.models import Job, utc_now
from research_platform.modules.execution.schemas import JobCreate
from research_platform.modules.execution.service import claim_job, finish_job, submit_job
from research_platform.modules.execution.worker import run_once


def enqueue(session):
    return submit_job(
        session, 1, JobCreate(job_type="system.check", idempotency_key="diagnostic-request")
    )


def test_job_survives_session_restart_and_diagnostic_finishes(session, database_url):
    job_id = enqueue(session).id
    engine = make_engine(database_url)
    with Session(engine) as restarted:
        assert run_once(restarted)
        row = restarted.get(Job, job_id)
        assert row.state == "SUCCEEDED"
        assert row.result == {"database": "reachable"}
        assert row.attempts == 1
    engine.dispose()


def test_second_claim_is_rejected_and_stale_worker_cannot_publish(session):
    enqueue(session)
    now = utc_now()
    old = claim_job(session, now - timedelta(seconds=70))
    current = claim_job(session, now)
    assert old and current and old.job_id == current.job_id and old.token != current.token
    assert claim_job(session, now) is None
    assert not finish_job(session, old, {"wrong": "stale result"})
    assert finish_job(session, current, {"correct": True})
    assert session.get(Job, current.job_id, populate_existing=True).result == {"correct": True}


def test_expired_attempt_budget_becomes_explicit_failure(session):
    job = enqueue(session)
    now = utc_now()
    for attempt in range(3):
        assert claim_job(session, now + timedelta(seconds=70 * attempt))
    assert claim_job(session, now + timedelta(seconds=210)) is None
    row = session.get(Job, job.id, populate_existing=True)
    assert row.state == "FAILED"
    assert row.error_code == "LEASE_EXHAUSTED"


def test_unknown_handler_fails_without_claiming_research_success(session):
    job = enqueue(session)
    job.job_type = "unregistered.research"
    session.commit()
    assert run_once(session)
    row = session.get(Job, job.id, populate_existing=True)
    assert row.state == "FAILED"
    assert row.error_code == "HANDLER_NOT_REGISTERED"
