"""API contracts for first-board background classification."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .first_board_classifier import PositionBand, ShortPath, Trend


class GroupRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    source_group_code: str
    description: str
    class_codes: list[str]


class ClassRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    group_code: str
    group_name: str
    source_detail_code: str
    source_group_code: str
    condition: str
    position_scope: Literal["high", "mid_or_low", "low", "mid", "any"]
    trend: Trend | None
    short_path: ShortPath | None


class ClassifierCatalogRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    taxonomy_version: Literal["first-board-background-v1"] = "first-board-background-v1"
    class_count: int = Field(ge=1)
    group_count: int = Field(ge=1)
    position_window_trading_days: Literal[60] = 60
    low_position_max_pct: Decimal
    high_position_min_pct: Decimal
    groups: list[GroupRead]
    classes: list[ClassRead]
    notes: list[str]


class ClassificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position_60d_pct: Decimal | None = Field(default=None, ge=0, le=100)
    trend: Trend
    short_path: ShortPath


class ClassificationRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    taxonomy_version: Literal["first-board-background-v1"] = "first-board-background-v1"
    class_code: str
    class_name: str
    group_code: str
    group_name: str
    source_detail_code: str
    position_60d_pct: Decimal | None
    position_band: PositionBand
    trend: Trend
    short_path: ShortPath
    classification_cutoff: Literal["T-1"] = "T-1"
    input_time_assurance: Literal["caller_declared"] = "caller_declared"
    uses_forward_data: Literal[False] = False
    explanation: str


class DatasetSourceRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_version_id: int
    source_task_id: str
    source_sha256: str
    ledger_sha256: str
    event_count: int = Field(ge=0)
    verification_status: Literal["pass"] = "pass"


class FirstBoardEventRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    stock_code: str
    event_date: date
    class_code: str
    class_name: str
    group_code: str
    group_name: str
    source_detail_code: str
    source_group_code: str
    position_60d_pct: Decimal | None
    position_band: PositionBand
    trend: Trend
    short_path: ShortPath


class FirstBoardEventListRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    taxonomy_version: Literal["first-board-background-v1"] = "first-board-background-v1"
    stock_code: str
    event_date: date | None = None
    items: list[FirstBoardEventRead]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    source: DatasetSourceRead
