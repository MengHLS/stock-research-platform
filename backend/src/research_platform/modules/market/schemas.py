from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Provider = Literal["tencent", "eastmoney", "sina", "tushare"]
Period = Literal["m1", "m5", "m15", "m30", "m60"]
Phase = Literal["opening_auction", "pre_open", "continuous", "lunch_break", "closed"]


class BarRead(BaseModel):
    """One intraday bar. Prices are decimal strings, volume is in shares."""

    model_config = ConfigDict(extra="forbid")

    start: datetime = Field(description="Bar start, ISO 8601 UTC")
    trading_day: date = Field(description="Exchange trading day, Asia/Shanghai")
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume_shares: Decimal = Field(description="Volume converted to shares")


class IntradaySeries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(description="Canonical symbol, suffix form, e.g. 600519.SH")
    period: Period
    provider: Literal["tencent"] = "tencent"
    bars: list[BarRead]
    total: int
    limits: list[str] = Field(
        default_factory=list, description="Provider limits that apply to this response"
    )


class AuctionSnapshotRead(BaseModel):
    """One minute of the 09:15–09:25 virtual matching curve."""

    model_config = ConfigDict(extra="forbid")

    time: datetime
    price: Decimal


class AuctionRead(BaseModel):
    """Opening call auction for one trading day.

    ``snapshots`` is the virtual-match curve; the ``matched_*`` fields are the
    result that actually traded. Before 09:25 the curve exists but nothing has
    matched, so the matched fields are null instead of zero.

    ``provider`` names the source that produced this response: ``eastmoney`` when
    the full 09:15–09:25 curve is available, ``sina`` when Eastmoney could not be
    reached and the 09:25 matched trade came from Sina instead, ``tencent`` as the
    last fallback. ``degraded`` is true in the latter two cases, so a client never
    shows an empty curve as if the instrument had no auction.
    """

    model_config = ConfigDict(extra="forbid")

    symbol: str
    trading_day: date
    provider: Literal["eastmoney", "sina", "tencent"]
    degraded: bool = False
    phase: Phase
    pre_close: Decimal | None = None
    snapshots: list[AuctionSnapshotRead]
    matched_time: datetime | None = None
    matched_price: Decimal | None = None
    matched_volume_shares: Decimal | None = None
    matched_amount: Decimal | None = None
    limits: list[str] = Field(default_factory=list)


class DailyBarRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trading_day: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume_shares: Decimal
    amount: Decimal


class DailySeries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    provider: Literal["tushare"] = "tushare"
    bars: list[DailyBarRead]
    total: int


class QuoteRead(BaseModel):
    """Real-time snapshot. Volume is 手 (see ``volume_note``); amount is 元.

    A snapshot is not a bar: it carries the last price at ``quote_time`` and the
    exchange's limit-up/limit-down prices. The volume unit differs between stocks,
    ETFs and indices at the provider, so the field is named ``volume_lots`` and
    ``amount`` is the reconcilable quantity.
    """

    model_config = ConfigDict(extra="forbid")

    symbol: str
    name: str
    price: Decimal
    previous_close: Decimal
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    quote_time: datetime = Field(description="Provider quote timestamp, ISO 8601 UTC")
    change_pct: Decimal | None = Field(default=None, description="Percent: 1 means 1%")
    volume_lots: Decimal = Field(description="Provider volume in 手; see volume_note")
    amount: Decimal = Field(description="Turnover in 元")
    turnover_pct: Decimal | None = Field(default=None, description="Percent: 1 means 1%")
    limit_up: Decimal | None = None
    limit_down: Decimal | None = None
    volume_note: str = Field(
        default=("腾讯快照成交量按手；指数与个别品种口径不同，股数以日内K线的 volume_shares 为准。")
    )
    phase: Phase


class StockProfileRead(BaseModel):
    """Static stock identity used by review detail views."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(description="Canonical symbol, suffix form")
    name: str
    industry: str | None = Field(
        default=None,
        description="Provider industry classification; null means explicitly unavailable.",
    )
    provider: Literal["eastmoney"] = "eastmoney"


class SourceStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Provider
    configured: bool
    capabilities: list[str]
    note: str


class SourceStatusList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[SourceStatus]
    upstream_enabled: bool


class MarketSessionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase: Phase


GlobalMarketGroup = Literal["us", "asia", "cn", "commodity"]
GlobalMarketAssessment = Literal["available", "partial", "missing"]


class GlobalMarketIssueRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal["quote_missing", "quote_stale", "history_missing", "history_stale"]
    scope: str
    message: str


class GlobalMarketQuoteRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price: Decimal
    previous_close: Decimal | None = None
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    change: Decimal | None = None
    change_pct: Decimal | None = Field(default=None, description="Percent: 1 means 1%")
    quote_time: datetime | None = None


class GlobalMarketBarRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    change_pct: Decimal | None = Field(default=None, description="Percent: 1 means 1%")


class GlobalMarketItemRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    name: str
    symbol: str
    group: GlobalMarketGroup
    market: str
    currency: str
    unit: str
    precision: int = Field(ge=0, le=4)
    provider: str | None = None
    assessment: GlobalMarketAssessment
    quote: GlobalMarketQuoteRead | None = None
    bars: list[GlobalMarketBarRead] = Field(default_factory=list)
    issues: list[GlobalMarketIssueRead] = Field(default_factory=list)


class GlobalMarketOverviewRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["sina", "yahoo", "eastmoney", "mixed"] = "mixed"
    as_of: datetime | None = None
    last_synced_at: datetime | None = None
    stale: bool = False
    window_requested: int = Field(ge=20, le=120)
    items: list[GlobalMarketItemRead]
    methodology: str
