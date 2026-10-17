import uuid

from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from research_platform.core.database import Base


class CatalogEntry(Base):
    __tablename__ = "catalog_entry"
    __table_args__ = (Index("ix_catalog_owner_id", "owner_user_id", "id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), default="", nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
