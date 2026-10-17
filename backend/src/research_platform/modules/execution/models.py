import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from research_platform.core.database import Base


def utc_now() -> datetime:
    """Database timestamps are naive UTC; API serialization supplies the timezone."""
    return datetime.now(UTC).replace(tzinfo=None)


class Job(Base):
    __tablename__ = "execution_job"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "idempotency_key", name="uq_job_owner_key"),
        Index("ix_job_queue", "state", "created_at"),
        Index("ix_job_owner", "owner_user_id", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    job_type: Mapped[str] = mapped_column(String(60), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(80), nullable=False)
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(16), default="QUEUED", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime)
    result: Mapped[dict | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
