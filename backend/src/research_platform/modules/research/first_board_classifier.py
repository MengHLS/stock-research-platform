"""Deterministic first-board background taxonomy.

The sixteen classes are a semantic renumbering of the frozen detail classes
from FIRSTBOARD-DETAIL-CLASSES-V1-20261025. Classification uses only the
background axes known through T-1; it never consumes forward returns or later
market structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

TAXONOMY_VERSION = "first-board-background-v1"
POSITION_WINDOW_TRADING_DAYS = 60
LOW_POSITION_MAX_PCT = Decimal("35")
HIGH_POSITION_MIN_PCT = Decimal("75")


class PositionBand(StrEnum):
    LOW = "low"
    MID = "mid"
    HIGH = "high"
    UNKNOWN = "unknown"


class Trend(StrEnum):
    UP = "up"
    DOWN = "down"
    SIDEWAYS = "sideways"
    UNKNOWN = "unknown"


class ShortPath(StrEnum):
    UP_CONTINUATION = "up_continuation"
    UP_PULLBACK = "up_pullback"
    DOWN_CONTINUATION = "down_continuation"
    DOWN_REBOUND = "down_rebound"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class GroupDefinition:
    code: str
    name: str
    source_group_code: str
    description: str


@dataclass(frozen=True, slots=True)
class ClassDefinition:
    code: str
    name: str
    group_code: str
    source_detail_code: str
    source_group_code: str
    condition: str
    position_scope: str
    trend: Trend | None
    short_path: ShortPath | None


@dataclass(frozen=True, slots=True)
class Classification:
    definition: ClassDefinition
    group: GroupDefinition
    position: PositionBand
    trend: Trend
    short_path: ShortPath


class UnsupportedAxisCombination(ValueError):
    """The axes are known but do not map to one of the frozen detail classes."""


GROUPS = (
    GroupDefinition(
        "FBG-01",
        "上升趋势·短期回调背景",
        "G1",
        "整体趋势向上且短期回撤的首板背景；不认证回调结束或后续恢复。",
    ),
    GroupDefinition(
        "FBG-02",
        "下降趋势·短期续跌背景",
        "G2",
        "整体趋势向下且短期继续走弱的首板背景；不认证首次转强或底部。",
    ),
    GroupDefinition(
        "FBG-03",
        "下降趋势·短期反弹背景",
        "G3",
        "整体趋势向下但短期出现反弹的首板背景；不认证趋势反转。",
    ),
    GroupDefinition(
        "FBG-04",
        "整体方向未明确·短期路径分化背景",
        "G4",
        "未形成明确上升或下降趋势，按短期路径区分的五类首板背景。",
    ),
    GroupDefinition(
        "FBG-05",
        "上升趋势·短期延续背景",
        "G5",
        "整体趋势向上且短期继续走强的首板背景；不等于低风险或高位加速。",
    ),
    GroupDefinition(
        "FBG-06",
        "趋势明确·短期中性背景",
        "R1",
        "整体趋势方向明确但短期路径中性的首板背景。",
    ),
    GroupDefinition(
        "FBG-07",
        "背景信息不足",
        "U1",
        "趋势或短期路径未知，无法归入前六组；不是股票质量评价。",
    ),
)

CLASSES = (
    ClassDefinition(
        "FBC-01",
        "高位上升趋势·短期回调背景首板",
        "FBG-01",
        "G1-H",
        "G1",
        "position=HIGH；trend=UP；shortPath=UP_PULLBACK",
        "high",
        Trend.UP,
        ShortPath.UP_PULLBACK,
    ),
    ClassDefinition(
        "FBC-02",
        "中低位上升趋势·短期回调背景首板",
        "FBG-01",
        "G1-ML",
        "G1",
        "position=MID或LOW；trend=UP；shortPath=UP_PULLBACK",
        "mid_or_low",
        Trend.UP,
        ShortPath.UP_PULLBACK,
    ),
    ClassDefinition(
        "FBC-03",
        "低位下降趋势·短期续跌背景首板",
        "FBG-02",
        "G2-L",
        "G2",
        "position=LOW；trend=DOWN；shortPath=DOWN_CONTINUATION",
        "low",
        Trend.DOWN,
        ShortPath.DOWN_CONTINUATION,
    ),
    ClassDefinition(
        "FBC-04",
        "中位下降趋势·短期续跌背景首板",
        "FBG-02",
        "G2-M",
        "G2",
        "position=MID；trend=DOWN；shortPath=DOWN_CONTINUATION",
        "mid",
        Trend.DOWN,
        ShortPath.DOWN_CONTINUATION,
    ),
    ClassDefinition(
        "FBC-05",
        "低位下降趋势·短期反弹背景首板",
        "FBG-03",
        "G3-L",
        "G3",
        "position=LOW；trend=DOWN；shortPath=DOWN_REBOUND",
        "low",
        Trend.DOWN,
        ShortPath.DOWN_REBOUND,
    ),
    ClassDefinition(
        "FBC-06",
        "中位下降趋势·短期反弹背景首板",
        "FBG-03",
        "G3-M",
        "G3",
        "position=MID；trend=DOWN；shortPath=DOWN_REBOUND",
        "mid",
        Trend.DOWN,
        ShortPath.DOWN_REBOUND,
    ),
    ClassDefinition(
        "FBC-07",
        "整体方向未明确·短期中性背景首板",
        "FBG-04",
        "G4-N",
        "G4",
        "trend=SIDEWAYS；shortPath=NEUTRAL",
        "any",
        Trend.SIDEWAYS,
        ShortPath.NEUTRAL,
    ),
    ClassDefinition(
        "FBC-08",
        "整体方向未明确·短期向上延续背景首板",
        "FBG-04",
        "G4-UC",
        "G4",
        "trend=SIDEWAYS；shortPath=UP_CONTINUATION",
        "any",
        Trend.SIDEWAYS,
        ShortPath.UP_CONTINUATION,
    ),
    ClassDefinition(
        "FBC-09",
        "整体方向未明确·短期上升回调背景首板",
        "FBG-04",
        "G4-PB",
        "G4",
        "trend=SIDEWAYS；shortPath=UP_PULLBACK",
        "any",
        Trend.SIDEWAYS,
        ShortPath.UP_PULLBACK,
    ),
    ClassDefinition(
        "FBC-10",
        "整体方向未明确·短期向下延续背景首板",
        "FBG-04",
        "G4-DC",
        "G4",
        "trend=SIDEWAYS；shortPath=DOWN_CONTINUATION",
        "any",
        Trend.SIDEWAYS,
        ShortPath.DOWN_CONTINUATION,
    ),
    ClassDefinition(
        "FBC-11",
        "整体方向未明确·短期下降反弹背景首板",
        "FBG-04",
        "G4-RB",
        "G4",
        "trend=SIDEWAYS；shortPath=DOWN_REBOUND",
        "any",
        Trend.SIDEWAYS,
        ShortPath.DOWN_REBOUND,
    ),
    ClassDefinition(
        "FBC-12",
        "高位上升趋势短期延续背景首板",
        "FBG-05",
        "G5-H",
        "G5",
        "position=HIGH；trend=UP；shortPath=UP_CONTINUATION",
        "high",
        Trend.UP,
        ShortPath.UP_CONTINUATION,
    ),
    ClassDefinition(
        "FBC-13",
        "中低位上升趋势短期延续背景首板",
        "FBG-05",
        "G5-ML",
        "G5",
        "position=MID或LOW；trend=UP；shortPath=UP_CONTINUATION",
        "mid_or_low",
        Trend.UP,
        ShortPath.UP_CONTINUATION,
    ),
    ClassDefinition(
        "FBC-14",
        "上升趋势·短期中性背景首板",
        "FBG-06",
        "R1-UP",
        "R1",
        "trend=UP；shortPath=NEUTRAL",
        "any",
        Trend.UP,
        ShortPath.NEUTRAL,
    ),
    ClassDefinition(
        "FBC-15",
        "下降趋势·短期中性背景首板",
        "FBG-06",
        "R1-DN",
        "R1",
        "trend=DOWN；shortPath=NEUTRAL",
        "any",
        Trend.DOWN,
        ShortPath.NEUTRAL,
    ),
    ClassDefinition(
        "FBC-16",
        "趋势或短期路径未知首板",
        "FBG-07",
        "U1-U",
        "U1",
        "trend=UNKNOWN或shortPath=UNKNOWN",
        "any",
        None,
        None,
    ),
)

GROUPS_BY_CODE = {group.code: group for group in GROUPS}
CLASSES_BY_CODE = {item.code: item for item in CLASSES}
SOURCE_DETAIL_CLASS_TO_CODE = {item.source_detail_code: item.code for item in CLASSES}


def position_band(position_60d_pct: Decimal | None) -> PositionBand:
    """Apply the frozen 60-session LOW/MID/HIGH boundaries exactly."""
    if position_60d_pct is None:
        return PositionBand.UNKNOWN
    if not Decimal("0") <= position_60d_pct <= Decimal("100"):
        raise ValueError("position_60d_pct must be between 0 and 100")
    if position_60d_pct <= LOW_POSITION_MAX_PCT:
        return PositionBand.LOW
    if position_60d_pct >= HIGH_POSITION_MIN_PCT:
        return PositionBand.HIGH
    return PositionBand.MID


def _group_for_axes(trend: Trend, short_path: ShortPath) -> GroupDefinition:
    if trend is Trend.UNKNOWN or short_path is ShortPath.UNKNOWN:
        return GROUPS_BY_CODE["FBG-07"]
    if trend is Trend.SIDEWAYS:
        return GROUPS_BY_CODE["FBG-04"]

    pair = {
        (Trend.UP, ShortPath.UP_PULLBACK): "FBG-01",
        (Trend.DOWN, ShortPath.DOWN_CONTINUATION): "FBG-02",
        (Trend.DOWN, ShortPath.DOWN_REBOUND): "FBG-03",
        (Trend.UP, ShortPath.UP_CONTINUATION): "FBG-05",
        (Trend.UP, ShortPath.NEUTRAL): "FBG-06",
        (Trend.DOWN, ShortPath.NEUTRAL): "FBG-06",
    }.get((trend, short_path))
    if pair is None:
        raise UnsupportedAxisCombination
    return GROUPS_BY_CODE[pair]


def _class_for_axes(
    group: GroupDefinition,
    position: PositionBand,
    trend: Trend,
    short_path: ShortPath,
) -> ClassDefinition:
    if group.code == "FBG-07":
        return CLASSES_BY_CODE["FBC-16"]
    if group.code == "FBG-01":
        if position is PositionBand.HIGH:
            return CLASSES_BY_CODE["FBC-01"]
        if position in {PositionBand.MID, PositionBand.LOW}:
            return CLASSES_BY_CODE["FBC-02"]
    elif group.code == "FBG-02":
        if position is PositionBand.LOW:
            return CLASSES_BY_CODE["FBC-03"]
        if position is PositionBand.MID:
            return CLASSES_BY_CODE["FBC-04"]
    elif group.code == "FBG-03":
        if position is PositionBand.LOW:
            return CLASSES_BY_CODE["FBC-05"]
        if position is PositionBand.MID:
            return CLASSES_BY_CODE["FBC-06"]
    elif group.code == "FBG-04":
        code = {
            ShortPath.NEUTRAL: "FBC-07",
            ShortPath.UP_CONTINUATION: "FBC-08",
            ShortPath.UP_PULLBACK: "FBC-09",
            ShortPath.DOWN_CONTINUATION: "FBC-10",
            ShortPath.DOWN_REBOUND: "FBC-11",
        }[short_path]
        return CLASSES_BY_CODE[code]
    elif group.code == "FBG-05":
        if position is PositionBand.HIGH:
            return CLASSES_BY_CODE["FBC-12"]
        if position in {PositionBand.MID, PositionBand.LOW}:
            return CLASSES_BY_CODE["FBC-13"]
    elif group.code == "FBG-06":
        if trend is Trend.UP:
            return CLASSES_BY_CODE["FBC-14"]
        if trend is Trend.DOWN:
            return CLASSES_BY_CODE["FBC-15"]

    raise UnsupportedAxisCombination


def classify(
    position_60d_pct: Decimal | None,
    trend: Trend,
    short_path: ShortPath,
) -> Classification:
    """Return the sole background class or reject an unsupported known combo."""
    position = position_band(position_60d_pct)
    return classify_labels(position, trend, short_path)


def classify_labels(position: PositionBand, trend: Trend, short_path: ShortPath) -> Classification:
    """Classify frozen axis labels without recomputing the original features."""
    group = _group_for_axes(trend, short_path)
    definition = _class_for_axes(group, position, trend, short_path)
    return Classification(
        definition=definition,
        group=group,
        position=position,
        trend=trend,
        short_path=short_path,
    )
