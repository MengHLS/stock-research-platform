from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from research_platform.core.database import session_dependency
from research_platform.modules.identity.dependencies import Actor, require_actor

from . import service
from .schemas import EntryCreate, EntryList, EntryRead

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])
ActorDep = Annotated[Actor, Depends(require_actor)]
SessionDep = Annotated[Session, Depends(session_dependency)]


@router.get("", response_model=EntryList, operation_id="list_catalog_entries")
def list_entries(
    actor: ActorDep,
    session: SessionDep,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    return service.list_entries(session, actor.user_id, offset, limit)


@router.get("/{entry_id}", response_model=EntryRead, operation_id="get_catalog_entry")
def get_entry(entry_id: str, actor: ActorDep, session: SessionDep):
    return service.get_entry(session, actor.user_id, entry_id)


@router.post("", response_model=EntryRead, status_code=201, operation_id="create_catalog_entry")
def create_entry(data: EntryCreate, actor: ActorDep, session: SessionDep):
    return service.create_entry(session, actor.user_id, data)
