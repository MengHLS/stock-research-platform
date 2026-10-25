"""HTTP endpoints for the imported first-board recursive structure snapshot."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request

from research_platform.core.errors import ErrorResponse
from research_platform.modules.identity.dependencies import Actor, require_actor

from .schemas import SnapshotRead, TargetDetailRead
from .service import FirstBoardRecursiveService

router = APIRouter(prefix="/api/v1/research/first-board-recursive", tags=["research"])
ActorDep = Annotated[Actor, Depends(require_actor)]


@router.get(
    "/snapshots/current",
    response_model=SnapshotRead,
    responses={404: {"model": ErrorResponse, "description": "No snapshot for the requested date"}},
    operation_id="get_first_board_recursive_snapshot",
)
def get_snapshot(
    request: Request,
    _actor: ActorDep,
    trade_date: date | None = Query(default=None),
):
    """Snapshot metadata, declared and derived counts, and the target summaries."""
    service: FirstBoardRecursiveService = request.app.state.first_board_recursive
    return service.snapshot(trade_date)


@router.get(
    "/targets/{symbol}",
    response_model=TargetDetailRead,
    responses={
        404: {"model": ErrorResponse, "description": "Snapshot or target is not available"},
    },
    operation_id="get_first_board_recursive_target",
)
def get_target(
    request: Request,
    _actor: ActorDep,
    symbol: str = Path(min_length=1, max_length=16, description="Exchange-qualified stock code"),
    trade_date: date | None = Query(default=None),
):
    """Two-layer result, recursive-window timeline, candidates and legacy audit."""
    service: FirstBoardRecursiveService = request.app.state.first_board_recursive
    return service.target_detail(symbol, trade_date)
