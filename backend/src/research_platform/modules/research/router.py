"""HTTP endpoints for first-board background classification."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from research_platform.core.errors import ErrorResponse
from research_platform.modules.identity.dependencies import Actor, require_actor

from . import service
from .daily_service import FirstBoardDailyService
from .dataset_source import FrozenFirstBoardDatasetSource
from .schemas import (
    ClassificationRead,
    ClassificationRequest,
    ClassifierCatalogRead,
    FirstBoardDailyRead,
    FirstBoardEventListRead,
)

router = APIRouter(prefix="/api/v1/research/first-board-classifier", tags=["research"])
ActorDep = Annotated[Actor, Depends(require_actor)]


@router.get(
    "",
    response_model=ClassifierCatalogRead,
    operation_id="get_first_board_classifier_catalog",
)
def get_catalog(_actor: ActorDep):
    return service.catalog()


@router.post(
    "/classify",
    response_model=ClassificationRead,
    operation_id="classify_first_board_background",
)
def classify_first_board(data: ClassificationRequest, _actor: ActorDep):
    return service.classify(data)


@router.get(
    "/events",
    response_model=FirstBoardEventListRead,
    responses={502: {"model": ErrorResponse, "description": "Frozen dataset is invalid"}},
    operation_id="list_first_board_events",
)
def list_first_board_events(
    request: Request,
    _actor: ActorDep,
    stock_code: str = Query(min_length=6, max_length=9, pattern=r"^\d{6}(?:\.(?:SH|SZ|BJ))?$"),
    event_date: date | None = Query(default=None, alias="date"),
    limit: int = Query(default=20, ge=1, le=100),
):
    source: FrozenFirstBoardDatasetSource | None = request.app.state.first_board_dataset
    return service.events(source, stock_code, event_date, limit)


@router.get(
    "/daily", response_model=FirstBoardDailyRead, operation_id="list_stored_first_board_events"
)
def list_stored_first_board_events(
    request: Request,
    _actor: ActorDep,
    event_date: date | None = Query(default=None, alias="date"),
    offset: int = Query(default=0, ge=0, le=100000),
    limit: int = Query(default=100, ge=1, le=500),
    batch_id: str | None = Query(default=None, pattern=r"^[0-9a-f]{64}$"),
):
    daily: FirstBoardDailyService = request.app.state.first_board_daily
    return daily.daily(event_date, offset=offset, limit=limit, batch_id=batch_id)
