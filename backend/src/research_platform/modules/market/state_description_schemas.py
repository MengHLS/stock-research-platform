"""Versioned API contract for the market-state description layer."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LayerClassification = Literal[
    "improving",
    "weakening",
    "mixed",
    "strong",
    "weak",
    "conflicted",
    "unavailable",
]


class MarketStateLayerMetricRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    value: Decimal | None = None
    unit: Literal["pct", "pp"]


class MarketStateLayerRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: Literal["short_5d", "trend_20d", "structure_60d"]
    label: str
    window_days: int = Field(ge=1)
    status: Literal["available", "unavailable"]
    classification: LayerClassification
    base_date: date | None = None
    metrics: list[MarketStateLayerMetricRead]
    note: str


class MarketStateFactsRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csi300_return_1d_pct: Decimal | None = None
    advancer_ratio_pct: Decimal | None = None
    median_return_pct: Decimal | None = None
    above_ma20_ratio_pct: Decimal | None = None
    above_ma60_ratio_pct: Decimal | None = None
    amount_ratio_20: Decimal | None = None
    amount_rolling_120_midrank: Decimal | None = None
    csi300_volatility_20_pct: Decimal | None = None
    csi300_drawdown_60_pct: Decimal | None = None
    limit_up_close_count: int | None = None
    limit_down_close_count: int | None = None
    broken_board_rate_pct: Decimal | None = None
    yesterday_limit_up_feedback_avg_return_pct: Decimal | None = None
    yesterday_limit_up_feedback_win_rate_pct: Decimal | None = None


class MarketStateConflictRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class MarketStateIssueRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class MarketStateDescriptionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    universe_id: str
    feature_version: str
    description_version: Literal["market-description-v1"] = "market-description-v1"
    build_version: str
    usage: Literal["descriptive_not_predictive"] = "descriptive_not_predictive"
    certification_level: str
    coverage_status: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    summary: str
    layers: list[MarketStateLayerRead]
    facts: MarketStateFactsRead
    conflicts: list[MarketStateConflictRead]
    issues: list[MarketStateIssueRead]
