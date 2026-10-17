from sqlalchemy import func, select
from sqlalchemy.orm import Session

from research_platform.core.errors import DomainError

from .models import CatalogEntry
from .schemas import EntryCreate, EntryList, EntryRead


def list_entries(session: Session, owner_id: int, offset: int, limit: int) -> EntryList:
    scope = CatalogEntry.owner_user_id == owner_id
    total = session.scalar(select(func.count()).select_from(CatalogEntry).where(scope)) or 0
    rows = session.scalars(
        select(CatalogEntry).where(scope).order_by(CatalogEntry.id).offset(offset).limit(limit)
    ).all()
    return EntryList(
        items=[EntryRead.model_validate(row) for row in rows],
        total=total,
        offset=offset,
        limit=limit,
    )


def get_entry(session: Session, owner_id: int, entry_id: str) -> CatalogEntry:
    row = session.scalar(
        select(CatalogEntry).where(
            CatalogEntry.id == entry_id, CatalogEntry.owner_user_id == owner_id
        )
    )
    if row is None:
        raise DomainError("ENTRY_NOT_FOUND")
    return row


def create_entry(session: Session, owner_id: int, data: EntryCreate) -> CatalogEntry:
    row = CatalogEntry(owner_user_id=owner_id, **data.model_dump())
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
