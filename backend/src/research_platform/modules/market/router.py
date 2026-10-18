from collections.abc import Callable
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from research_platform.core.errors import DomainError, ErrorField

from .market_time import session_phase
from .schemas import (
    AuctionRead,
    DailySeries,
    IntradaySeries,
    MarketSessionRead,
    Period,
    QuoteRead,
    SourceStatusList,
)
from .service import MarketService

router = APIRouter(prefix="/api/v1/market", tags=["market"])

# Symbols are accepted in several spellings; the canonical form is 600519.SH.
SymbolQuery = Annotated[
    str,
    Query(
        min_length=1,
        max_length=16,
        description="规范形态 600519.SH；也接受 600519 / sh600519 / sh.600519 / 600519.sh",
    ),
]
# SSE index codes reuse SZSE stock digits (000xxx), so they must name the exchange.
AmbiguousSymbolNote = "上证指数号段（000001/000016/000300/000905 等）必须带交易所"


def reject_unknown_query(request: Request, allowed: frozenset[str]) -> None:
    """Fail on query parameters this endpoint does not define.

    FastAPI ignores unknown parameters in a plain signature, so a typo like
    ``?smybol=600519`` used to return the *default* instrument with HTTP 200 —
    a silently wrong answer. The project rule is that requests reject extra
    fields; query parameters follow the same rule.
    """
    unknown = sorted(set(request.query_params) - allowed)
    if unknown:
        raise DomainError(
            "REQUEST_INVALID",
            fields=[ErrorField(path=f"query.{name}", code="unknown_parameter") for name in unknown],
        )


def require_query(allowed: frozenset[str]) -> Callable[[Request], None]:
    """Dependency factory binding one endpoint's allowed query parameter names."""

    def dependency(request: Request) -> None:
        reject_unknown_query(request, allowed)

    return dependency


def market_service(request: Request) -> MarketService:
    return request.app.state.market


ServiceDep = Annotated[MarketService, Depends(market_service)]


@router.get(
    "/intraday",
    response_model=IntradaySeries,
    operation_id="get_intraday_kline",
    dependencies=[Depends(require_query(frozenset({"symbol", "period", "limit"})))],
)
def get_intraday(
    service: ServiceDep,
    symbol: SymbolQuery,
    period: Annotated[Period, Query()] = "m1",
    limit: Annotated[int, Query(ge=1, le=800)] = 240,
):
    """日内K线（腾讯公共源）；短期缓存，不落库。"""
    return service.intraday(symbol, period, limit)


@router.get(
    "/quote",
    response_model=QuoteRead,
    operation_id="get_quote",
    dependencies=[Depends(require_query(frozenset({"symbol"})))],
)
def get_quote(service: ServiceDep, symbol: SymbolQuery):
    """实时快照（腾讯）：最新价、涨跌停价与行情时间；覆盖北交所与指数。"""
    return service.quote(symbol)


@router.get(
    "/auction",
    response_model=AuctionRead,
    operation_id="get_opening_auction",
    dependencies=[Depends(require_query(frozenset({"symbol"})))],
)
def get_auction(service: ServiceDep, symbol: SymbolQuery):
    """开盘集合竞价：09:15–09:25 虚拟撮合曲线 + 实际成交结果。"""
    return service.auction(symbol)


@router.get(
    "/daily",
    response_model=DailySeries,
    operation_id="get_daily_kline",
    dependencies=[Depends(require_query(frozenset({"symbol", "start", "end"})))],
)
def get_daily(
    service: ServiceDep,
    symbol: SymbolQuery,
    start: Annotated[date | None, Query()] = None,
    end: Annotated[date | None, Query()] = None,
):
    """日线（Tushare）；需要 RP_TUSHARE__TOKEN。"""
    return service.daily(symbol, start, end)


@router.get(
    "/sources",
    response_model=SourceStatusList,
    operation_id="list_market_sources",
    dependencies=[Depends(require_query(frozenset()))],
)
def list_sources(service: ServiceDep):
    """各外部数据源是否可用，以及本版本支持的能力。"""
    return service.sources()


@router.get(
    "/session",
    response_model=MarketSessionRead,
    operation_id="get_market_session",
    dependencies=[Depends(require_query(frozenset()))],
)
def get_session():
    """当前交易时段标签（按时钟判断，不代表交易日历）。"""
    return MarketSessionRead(phase=session_phase())
