"""Application-database publication and read access for recursive snapshots."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from research_platform.core.errors import DomainError

from .models import (
    FirstBoardRecursiveCandidate,
    FirstBoardRecursiveSnapshot,
    FirstBoardRecursiveTarget,
)

TARGET_CHUNK = 200
CANDIDATE_CHUNK = 500


class SqlFirstBoardRecursiveStore:
    def __init__(self, sessions: sessionmaker) -> None:
        self.sessions = sessions

    def publish(
        self,
        snapshot: dict,
        targets: list[dict],
        candidates: list[dict],
        *,
        replace: bool = False,
        now: datetime | None = None,
    ) -> str:
        """Write one immutable snapshot. Returns INSERTED, REPLACED or UNCHANGED."""
        values = {
            **snapshot,
            "computed_at": (now or datetime.now(UTC)).replace(tzinfo=None),
        }
        try:
            with self.sessions.begin() as session:
                existing = session.get(FirstBoardRecursiveSnapshot, values["snapshot_id"])
                if existing is not None:
                    if _same_snapshot(existing, values):
                        return "UNCHANGED"
                    if not replace:
                        raise DomainError("FIRST_BOARD_RECURSIVE_SNAPSHOT_CONFLICT")
                    session.execute(
                        delete(FirstBoardRecursiveCandidate).where(
                            FirstBoardRecursiveCandidate.snapshot_id == values["snapshot_id"]
                        )
                    )
                    session.execute(
                        delete(FirstBoardRecursiveTarget).where(
                            FirstBoardRecursiveTarget.snapshot_id == values["snapshot_id"]
                        )
                    )
                    session.execute(
                        delete(FirstBoardRecursiveSnapshot).where(
                            FirstBoardRecursiveSnapshot.snapshot_id == values["snapshot_id"]
                        )
                    )
                    state = "REPLACED"
                else:
                    state = "INSERTED"
                session.execute(FirstBoardRecursiveSnapshot.__table__.insert(), [values])
                target_values = [{**row, "snapshot_id": values["snapshot_id"]} for row in targets]
                candidate_values = [
                    {**row, "snapshot_id": values["snapshot_id"]} for row in candidates
                ]
                for offset in range(0, len(target_values), TARGET_CHUNK):
                    session.execute(
                        FirstBoardRecursiveTarget.__table__.insert(),
                        target_values[offset : offset + TARGET_CHUNK],
                    )
                for offset in range(0, len(candidate_values), CANDIDATE_CHUNK):
                    session.execute(
                        FirstBoardRecursiveCandidate.__table__.insert(),
                        candidate_values[offset : offset + CANDIDATE_CHUNK],
                    )
                stored_targets = session.scalar(
                    select(func.count())
                    .select_from(FirstBoardRecursiveTarget)
                    .where(FirstBoardRecursiveTarget.snapshot_id == values["snapshot_id"])
                )
                stored_candidates = session.scalar(
                    select(func.count())
                    .select_from(FirstBoardRecursiveCandidate)
                    .where(FirstBoardRecursiveCandidate.snapshot_id == values["snapshot_id"])
                )
                if (
                    stored_targets != values["target_count"]
                    or stored_candidates != values["candidate_link_count"]
                ):
                    raise DomainError("FIRST_BOARD_RECURSIVE_STORAGE_BAD_DATA")
                return state
        except SQLAlchemyError:
            raise DomainError("FIRST_BOARD_RECURSIVE_STORAGE_UNAVAILABLE") from None

    def snapshot(self, trade_date: date | None = None):
        """Return the newest stored snapshot, optionally restricted to one delivery day.

        One trade date normally carries exactly one delivery (one ``snapshot_id``).
        If a second batch for the same date were ever imported, ``computed_at``
        orders them deterministically and this read returns the newest; the API
        therefore treats ``trade_date`` as a delivery-day locator, not as a batch
        discriminator, and older same-day batches become unreachable by date.
        """
        try:
            with self.sessions() as session:
                statement = select(FirstBoardRecursiveSnapshot)
                if trade_date is not None:
                    statement = statement.where(
                        FirstBoardRecursiveSnapshot.trade_date == trade_date
                    )
                row = session.scalar(
                    statement.order_by(
                        FirstBoardRecursiveSnapshot.trade_date.desc(),
                        FirstBoardRecursiveSnapshot.computed_at.desc(),
                        FirstBoardRecursiveSnapshot.snapshot_id.desc(),
                    ).limit(1)
                )
                if row is not None:
                    session.expunge(row)
                return row
        except SQLAlchemyError:
            raise DomainError("FIRST_BOARD_RECURSIVE_STORAGE_UNAVAILABLE") from None

    def snapshots(self) -> list:
        try:
            with self.sessions() as session:
                rows = list(
                    session.scalars(
                        select(FirstBoardRecursiveSnapshot).order_by(
                            FirstBoardRecursiveSnapshot.trade_date.desc(),
                            FirstBoardRecursiveSnapshot.computed_at.desc(),
                        )
                    )
                )
                session.expunge_all()
                return rows
        except SQLAlchemyError:
            raise DomainError("FIRST_BOARD_RECURSIVE_STORAGE_UNAVAILABLE") from None

    def targets(self, snapshot_id: str) -> list:
        try:
            with self.sessions() as session:
                rows = list(
                    session.scalars(
                        select(FirstBoardRecursiveTarget)
                        .where(FirstBoardRecursiveTarget.snapshot_id == snapshot_id)
                        .order_by(FirstBoardRecursiveTarget.target_order)
                    )
                )
                session.expunge_all()
                return rows
        except SQLAlchemyError:
            raise DomainError("FIRST_BOARD_RECURSIVE_STORAGE_UNAVAILABLE") from None

    def target(self, snapshot_id: str, stock_code: str):
        try:
            with self.sessions() as session:
                row = session.get(FirstBoardRecursiveTarget, (snapshot_id, stock_code))
                if row is not None:
                    session.expunge(row)
                return row
        except SQLAlchemyError:
            raise DomainError("FIRST_BOARD_RECURSIVE_STORAGE_UNAVAILABLE") from None

    def candidates(self, snapshot_id: str, stock_code: str) -> list:
        try:
            with self.sessions() as session:
                rows = list(
                    session.scalars(
                        select(FirstBoardRecursiveCandidate)
                        .where(
                            FirstBoardRecursiveCandidate.snapshot_id == snapshot_id,
                            FirstBoardRecursiveCandidate.stock_code == stock_code,
                        )
                        .order_by(FirstBoardRecursiveCandidate.candidate_date)
                    )
                )
                session.expunge_all()
                return rows
        except SQLAlchemyError:
            raise DomainError("FIRST_BOARD_RECURSIVE_STORAGE_UNAVAILABLE") from None

    def derived_counts(self, snapshot_id: str) -> dict:
        """Counts derived from stored rows, not from the snapshot's declared totals."""
        try:
            with self.sessions() as session:
                targets = session.scalar(
                    select(func.count())
                    .select_from(FirstBoardRecursiveTarget)
                    .where(FirstBoardRecursiveTarget.snapshot_id == snapshot_id)
                )
                candidates = session.scalar(
                    select(func.count())
                    .select_from(FirstBoardRecursiveCandidate)
                    .where(FirstBoardRecursiveCandidate.snapshot_id == snapshot_id)
                )
                stages = session.execute(
                    select(
                        FirstBoardRecursiveTarget.result_stage,
                        func.count(),
                    )
                    .where(FirstBoardRecursiveTarget.snapshot_id == snapshot_id)
                    .group_by(FirstBoardRecursiveTarget.result_stage)
                ).all()
                reasons = session.execute(
                    select(
                        FirstBoardRecursiveTarget.selection_reason,
                        func.count(),
                    )
                    .where(FirstBoardRecursiveTarget.snapshot_id == snapshot_id)
                    .group_by(FirstBoardRecursiveTarget.selection_reason)
                ).all()
                return {
                    "targets": int(targets or 0),
                    "candidates": int(candidates or 0),
                    "stage_counts": {code: count for code, count in sorted(stages)},
                    "selection_reason_counts": {code: count for code, count in sorted(reasons)},
                }
        except SQLAlchemyError:
            raise DomainError("FIRST_BOARD_RECURSIVE_STORAGE_UNAVAILABLE") from None


def _same_snapshot(existing: FirstBoardRecursiveSnapshot, values: dict) -> bool:
    return all(
        getattr(existing, key) == values[key]
        for key in (
            "trade_date",
            "board_scope",
            "status",
            "source_sha256",
            "artifact_sha256",
            "verification_status",
            "target_count",
            "first_board_count",
            "candidate_link_count",
        )
    )
