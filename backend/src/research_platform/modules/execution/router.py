from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from research_platform.core.database import session_dependency
from research_platform.modules.identity.dependencies import Actor, require_actor

from . import service
from .schemas import JobCreate, JobRead

router = APIRouter(prefix="/api/v1/jobs", tags=["execution"])
ActorDep = Annotated[Actor, Depends(require_actor)]
SessionDep = Annotated[Session, Depends(session_dependency)]


@router.post("", response_model=JobRead, status_code=202, operation_id="submit_job")
def submit_job(data: JobCreate, actor: ActorDep, session: SessionDep):
    return service.submit_job(session, actor.user_id, data)


@router.get("/{job_id}", response_model=JobRead, operation_id="get_job")
def get_job(job_id: str, actor: ActorDep, session: SessionDep):
    return service.get_job(session, actor.user_id, job_id)
