import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from research_platform.core.errors import DomainError

from .models import Job, utc_now
from .schemas import JobCreate


def get_job(session: Session, owner_id: int, job_id: str) -> Job:
    row = session.scalar(select(Job).where(Job.id == job_id, Job.owner_user_id == owner_id))
    if row is None:
        raise DomainError("JOB_NOT_FOUND")
    return row


def submit_job(session: Session, owner_id: int, data: JobCreate) -> Job:
    digest = hashlib.sha256(data.job_type.encode()).hexdigest()
    existing = session.scalar(
        select(Job).where(
            Job.owner_user_id == owner_id, Job.idempotency_key == data.idempotency_key
        )
    )
    if existing:
        if existing.input_digest != digest:
            raise DomainError("IDEMPOTENCY_CONFLICT")
        return existing
    row = Job(
        owner_user_id=owner_id,
        job_type=data.job_type,
        idempotency_key=data.idempotency_key,
        input_digest=digest,
    )
    session.add(row)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        # The uniqueness constraint serializes concurrent repeats of the same request.
        existing = session.scalar(
            select(Job).where(
                Job.owner_user_id == owner_id, Job.idempotency_key == data.idempotency_key
            )
        )
        if existing is None or existing.input_digest != digest:
            raise DomainError("IDEMPOTENCY_CONFLICT") from None
        return existing
    session.refresh(row)
    return row


@dataclass(frozen=True)
class Lease:
    job_id: str
    token: str
    job_type: str


def claim_job(session: Session, now: datetime | None = None) -> Lease | None:
    now = now or utc_now()
    expired = and_(Job.state == "RUNNING", Job.lease_until < now)
    session.execute(
        update(Job)
        .where(expired, Job.attempts >= 3)
        .values(state="FAILED", error_code="LEASE_EXHAUSTED", lease_token=None, lease_until=None)
    )
    eligible = and_(
        Job.attempts < 3,
        or_(Job.state == "QUEUED", expired),
    )
    candidates = session.scalars(
        select(Job.id).where(eligible).order_by(Job.created_at, Job.id).limit(32)
    ).all()
    for job_id in candidates:
        token = str(uuid.uuid4())
        changed = session.execute(
            update(Job)
            .where(Job.id == job_id, eligible)
            .values(
                state="RUNNING",
                attempts=Job.attempts + 1,
                lease_token=token,
                lease_until=now + timedelta(seconds=60),
                error_code=None,
            )
        )
        if changed.rowcount == 1:
            session.commit()
            row = session.get(Job, job_id, populate_existing=True)
            assert row is not None
            return Lease(row.id, token, row.job_type)
    session.commit()
    return None


def finish_job(
    session: Session, lease: Lease, result: dict | None, error: str | None = None
) -> bool:
    changed = session.execute(
        update(Job)
        .where(
            Job.id == lease.job_id,
            Job.state == "RUNNING",
            Job.lease_token == lease.token,
            Job.lease_until >= utc_now(),
        )
        .values(
            state="FAILED" if error else "SUCCEEDED",
            result=result,
            error_code=error,
            lease_token=None,
            lease_until=None,
        )
    )
    session.commit()
    return changed.rowcount == 1
