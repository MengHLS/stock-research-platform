"""Typed API contract for historical market-review reads."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CoverageStatus = Literal["available", "missing"]
IssueCode = Literal[
    "source_presence_only",
    "calendar_derived_from_index_daily",
    "target_limit_up_missing",
    "previous_limit_up_missing",
    "board_history_exhausted",
    "stock_quote_missing",
    "history_window_truncated",
    "index_history_missing",
    "stock_history_missing",
    "market_state_counts_unavailable",
    "market_state_counts_not_configured",
    "market_state_counts_source_unavailable",
    "market_state_counts_source_bad_data",
    "market_state_counts_unverified",
]


class ReviewIssueRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: IssueCode
    scope: str
    message: str


class CoverageRead(BaseModel):
    """Row presence, not proof that the source contains every expected row."""

    model_config = ConfigDict(extra="forbid")

    status: CoverageStatus
    row_count: int = Field(ge=0)
    completeness: Literal["presence_only"] = "presence_only"


class IndexCoverageRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shanghai: CoverageRead
    shenzhen: CoverageRead
    csi300: CoverageRead
    csi500: CoverageRead


class ReviewDateRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    limit_up: CoverageRead
    market_wide: CoverageRead
    indices: IndexCoverageRead
    market_state_counts: CoverageRead | None = None
    market_state_coverage_status: str | None = None
    limit_up_close_count: int | None = Field(default=None, ge=0)
    limit_down_close_count: int | None = Field(default=None, ge=0)


class ReviewDatesRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: date
    end: date
    calendar_provider: Literal["legacy.index_daily"] = "legacy.index_daily"
    dates: list[ReviewDateRead]
    issues: list[ReviewIssueRead]
    methodology_version: Literal["market-review-v1"] = "market-review-v1"


class ReviewContextRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of_date: date
    default_date: date | None = None
    default_date_reason: Literal["latest_limit_up", "latest_calendar", "none"]
    requested_date: date | None = None
    requested_date_known: bool | None = None
    calendar_start: date | None = None
    calendar_end: date | None = None
    latest_limit_up_date: date | None = None
    previous_trading_day: date | None = None
    next_trading_day: date | None = None
    window_max: int = Field(ge=1)
    methodology_version: Literal["market-review-v1"] = "market-review-v1"


class ReviewSummaryRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessment: Literal["available", "partial", "missing"]
    total_limit_up: int | None = None
    first_board_count: int | None = None
    connection_board_count: int | None = None
    max_board: int | None = None
    three_board_plus_count: int | None = None
    broken_count: int | None = None
    broken_connection_count: int | None = None
    emotion_score: int | None = None


class LadderRowRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    name: str
    sector: str
    limit_up_time: str
    boards: int | None
    boards_as_of_date: date
    broken_kind: Literal["connection", "first"] | None = None
    change_pct: Decimal | None = None
    one_word_board: bool | None = None


class LadderRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection: list[LadderRowRead]
    first: list[LadderRowRead]
    broken: list[LadderRowRead]
    unknown: list[LadderRowRead]


class ThemeCountRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme: str
    count: int = Field(ge=1)


class MaxBoardStockRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    name: str


class HighBoardStockRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    name: str
    boards: int = Field(ge=6)


class OverviewIndexRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    name: str
    coverage: CoverageRead
    close: Decimal | None = None
    change_pct: Decimal | None = None


class MarketHistoryRowRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    assessment: Literal["available", "partial", "missing"]
    total_limit_up: int | None = None
    first_board_count: int | None = None
    connection_board_count: int | None = None
    max_board: int | None = None
    three_board_plus_count: int | None = None
    emotion_score: int | None = None
    broken_count: int | None = None
    broken_connection_count: int | None = None
    max_board_stock_total: int | None = None
    max_board_stocks: list[MaxBoardStockRead] = Field(default_factory=list)
    high_board_stocks: list[HighBoardStockRead] = Field(default_factory=list)
    unknown_fields: list[str] = Field(default_factory=list)
    turnover_100m_cny: Decimal | None = None
    margin_balance_100m_cny: Decimal | None = None
    themes: list[ThemeCountRead] = Field(default_factory=list)


class ReviewMethodologyRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["market-review-v1"] = "market-review-v1"
    calendar: str = "旧库 index_daily 的不同 tradeDate；不是独立交易日历。"
    board_chain: str = "按 index_daily 交易日连续涨停计数；缺口或窗口触顶返回 null。"
    emotion_formula: str = (
        "40×连板家数/涨停家数 + 30×min(最高板/10,1) + 30×三板以上家数/连板家数；四舍五入取整。"
    )
    completeness: str = "available 仅表示源中存在行，不宣称数据已完整采集。"
    market_wide_units: str = "market_data.turnover/marginBalance 按旧源亿元口径原样输出。"
    index_units: str = (
        "上证、深证、沪深300、中证500 取旧源并有金额/成交量；创业板指、科创50 "
        "取腾讯公开不复权日线并写入应用库，仅 OHLC，最多 160 根，早于覆盖范围保持缺失。"
    )


class ReviewOverviewRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    previous_trading_day: date | None
    window_requested: int
    window_actual: int
    coverage: dict[str, CoverageRead]
    summary: ReviewSummaryRead
    ladder: LadderRead
    themes: list[ThemeCountRead]
    market_wide: CoverageRead
    turnover_100m_cny: Decimal | None = None
    margin_balance_100m_cny: Decimal | None = None
    indices: list[OverviewIndexRead]
    history: list[MarketHistoryRowRead]
    issues: list[ReviewIssueRead]
    methodology: ReviewMethodologyRead


class ReviewIndexBarRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    change_pct: Decimal | None = None
    ma5: Decimal | None = None
    ma20: Decimal | None = None
    amount_source: Decimal | None = None
    volume_source: Decimal | None = None


class ReviewIndexSeriesRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    name: str
    coverage: CoverageRead
    missing_days: int = Field(ge=0)
    bars: list[ReviewIndexBarRead]


class ReviewIndicesRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    window_requested: int
    window_actual: int
    history_dates: list[date]
    indices: list[ReviewIndexSeriesRead]
    issues: list[ReviewIssueRead]
    methodology: ReviewMethodologyRead


class ReviewStockBarRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    change_pct: Decimal | None = None
    ma5: Decimal | None = None
    ma20: Decimal | None = None


class ReviewStockSeriesRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    window_requested: int
    window_actual: int
    coverage: CoverageRead
    missing_days: int = Field(ge=0)
    bars: list[ReviewStockBarRead]
    issues: list[ReviewIssueRead]
    methodology: ReviewMethodologyRead


class LimitUpReviewDayRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    assessment: Literal["available", "partial", "missing"]
    total_limit_up: int | None = None
    broken_count: int | None = None
    limit_up: CoverageRead


class LimitUpReviewRowRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    symbol: str
    name: str
    sector: str
    status: Literal["limit_up", "broken"]
    boards: int | None
    boards_as_of_date: date
    limit_up_time: str
    limit_up_time_as_of_date: date
    broken_kind: Literal["connection", "first"] | None = None
    change_pct: Decimal | None = None
    one_word_board: bool | None = None


class ReviewLimitUpRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    window_requested: int
    window_actual: int
    rows: list[LimitUpReviewRowRead]
    days: list[LimitUpReviewDayRead]
    issues: list[ReviewIssueRead]
    methodology: ReviewMethodologyRead
