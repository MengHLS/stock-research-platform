"""Deterministic, non-predictive descriptions of a frozen market-state row."""

from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Any, Literal

from research_platform.core.cache import TTLCache
from research_platform.core.config import MarketStateConfig
from research_platform.core.errors import DomainError

from .market_time import exchange_now
from .state_description_schemas import (
    MarketStateConflictRead,
    MarketStateDescriptionRead,
    MarketStateFactsRead,
    MarketStateIssueRead,
    MarketStateLayerMetricRead,
    MarketStateLayerRead,
)
from .state_source import MarketStateSource, MarketStateTable, source_or_error

DESCRIPTION_VERSION = "market-description-v1"
MIN_BREADTH_COVERAGE = Decimal("0.95")
MIN_AMOUNT_COVERAGE = Decimal("0.95")


class MarketStateDescriptionService:
    def __init__(
        self,
        source: MarketStateSource | None,
        config: MarketStateConfig | None,
        *,
        cache: TTLCache | None = None,
    ) -> None:
        self._source = source
        self._config = config
        self._cache = cache if cache is not None else TTLCache()

    def describe(self, trade_date: date | None = None, *, as_of: date | None = None):
        table = source_or_error(self._source)
        selected = self._select_date(table, trade_date, as_of or exchange_now().date())
        key = ("market-state-description", DESCRIPTION_VERSION, table.source_sha256, selected)
        try:
            return self._cache.get_or_create(
                key,
                self._config.cache_seconds if self._config else 0,
                lambda: describe_row(table, selected),
            )
        except DomainError:
            raise
        except (ArithmeticError, KeyError, TypeError, ValueError):
            raise DomainError("MARKET_STATE_SOURCE_BAD_DATA") from None

    def scan(self, start: date | None = None, end: date | None = None) -> dict[str, Any]:
        table = source_or_error(self._source)
        try:
            return scan_table(table, start, end)
        except DomainError:
            raise
        except (ArithmeticError, KeyError, TypeError, ValueError):
            raise DomainError("MARKET_STATE_SOURCE_BAD_DATA") from None

    @staticmethod
    def _select_date(table: MarketStateTable, requested: date | None, as_of: date) -> str:
        if requested is not None:
            day = requested.isoformat()
            if day > as_of.isoformat() or day not in table.by_date:
                raise DomainError("MARKET_STATE_DATE_UNAVAILABLE")
            return day
        eligible = [row["tradeDate"] for row in table.rows if row["tradeDate"] <= as_of.isoformat()]
        if not eligible:
            raise DomainError("MARKET_STATE_DATE_UNAVAILABLE")
        return str(eligible[-1])


def describe_row(table: MarketStateTable, trade_date: str) -> MarketStateDescriptionRead:
    if trade_date not in table.by_date:
        raise DomainError("MARKET_STATE_DATE_UNAVAILABLE")
    position = next(i for i, row in enumerate(table.rows) if row["tradeDate"] == trade_date)
    row = table.rows[position]
    base = table.rows[position - 5] if position >= 5 else None
    issues: list[MarketStateIssueRead] = []
    short = _short_layer(table, position, base)
    trend = _trend_layer(row)
    structure = _structure_layer(row)
    facts = _facts(row)
    issues.extend(_quality_issues(row, base, short, trend, structure))
    conflicts = _conflicts(row, facts, short, trend, structure)
    return MarketStateDescriptionRead(
        date=date.fromisoformat(trade_date),
        universe_id=table.universe_id,
        feature_version=table.feature_version,
        build_version=table.build_version,
        certification_level=table.certification_level,
        coverage_status=str(row.get("coverageStatus") or "UNKNOWN"),
        source_sha256=table.source_sha256,
        summary=_summary(row, facts, short, trend, structure),
        layers=[short, trend, structure],
        facts=facts,
        conflicts=conflicts,
        issues=issues,
    )


def scan_table(
    table: MarketStateTable,
    start: date | None = None,
    end: date | None = None,
) -> dict[str, Any]:
    start_text = start.isoformat() if start else table.rows[0]["tradeDate"]
    end_text = end.isoformat() if end else table.rows[-1]["tradeDate"]
    if start_text > end_text:
        raise DomainError("REQUEST_INVALID")
    rows = [row for row in table.rows if start_text <= row["tradeDate"] <= end_text]
    if not rows:
        raise DomainError("MARKET_STATE_DATE_UNAVAILABLE")
    descriptions = [describe_row(table, str(row["tradeDate"])) for row in rows]
    layers: dict[str, Any] = {}
    for key in ("short_5d", "trend_20d", "structure_60d"):
        selected_layers = [
            next(layer for layer in item.layers if layer.key == key) for item in descriptions
        ]
        values = [layer.classification for layer in selected_layers]
        layers[key] = _scan_layer(values)
        unavailable_years = Counter(
            item.date.year
            for item, layer in zip(descriptions, selected_layers, strict=True)
            if layer.status == "unavailable"
        )
        layers[key]["unavailable_by_year"] = {
            str(year): count for year, count in sorted(unavailable_years.items())
        }
    conflicts = Counter(conflict.code for item in descriptions for conflict in item.conflicts)
    issues = Counter(issue.code for item in descriptions for issue in item.issues)
    return {
        "description_version": DESCRIPTION_VERSION,
        "feature_version": table.feature_version,
        "universe_id": table.universe_id,
        "source_sha256": table.source_sha256,
        "start": start_text,
        "end": end_text,
        "row_count": len(rows),
        "layers": layers,
        "conflicts": dict(sorted(conflicts.items())),
        "issues": dict(sorted(issues.items())),
    }


def _short_layer(
    table: MarketStateTable,
    position: int,
    base: dict[str, Any] | None,
) -> MarketStateLayerRead:
    row = table.rows[position]
    close = _decimal(row, "csi300Close")
    base_close = _decimal(base, "csi300Close") if base else None
    breadth = _decimal(row, "aboveMa20RatioPct")
    base_breadth = _decimal(base, "aboveMa20RatioPct") if base else None
    metrics = [
        _metric("csi300_return_5d_pct", "沪深300 5日收益", None, "pct"),
        _metric("above_ma20_ratio_change_5d_pp", "MA20宽度5日变化", None, "pp"),
    ]
    if (
        base is None
        or close is None
        or base_close is None
        or close <= 0
        or base_close <= 0
        or breadth is None
        or base_breadth is None
        or not _valid_percentage(breadth)
        or not _valid_percentage(base_breadth)
        or not _breadth_coverage(row, "ma20EligibleCount")
        or not _breadth_coverage(base, "ma20EligibleCount")
    ):
        return MarketStateLayerRead(
            key="short_5d",
            label="5日变化",
            window_days=5,
            status="unavailable",
            classification="unavailable",
            base_date=date.fromisoformat(base["tradeDate"]) if base else None,
            metrics=metrics,
            note="缺少连续5个市场日、有效收盘或达标宽度覆盖，未判定变化方向。",
        )
    return_5d = (close / base_close - 1) * 100
    breadth_delta = breadth - base_breadth
    if return_5d > 0 and breadth_delta > 0:
        classification: Literal["improving", "weakening", "mixed"] = "improving"
        note = "指数5日收益与MA20宽度同向改善。"
    elif return_5d < 0 and breadth_delta < 0:
        classification = "weakening"
        note = "指数5日收益与MA20宽度同向恶化。"
    else:
        classification = "mixed"
        note = "指数收益与宽度变化方向不一致，或至少一项持平。"
    metrics[0].value = return_5d
    metrics[1].value = breadth_delta
    return MarketStateLayerRead(
        key="short_5d",
        label="5日变化",
        window_days=5,
        status="available",
        classification=classification,
        base_date=date.fromisoformat(base["tradeDate"]),
        metrics=metrics,
        note=note,
    )


def _trend_layer(row: dict[str, Any]) -> MarketStateLayerRead:
    close = _decimal(row, "csi300Close")
    ma20 = _decimal(row, "csi300Ma20")
    return_20d = _decimal(row, "csi300Return20dPct")
    breadth = _decimal(row, "aboveMa20RatioPct")
    metrics = [
        _metric("csi300_return_20d_pct", "沪深300 20日收益", return_20d, "pct"),
        _metric("above_ma20_ratio_pct", "MA20上方宽度", breadth, "pct"),
        _metric(
            "csi300_vs_ma20_pct",
            "沪深300相对MA20",
            (close / ma20 - 1) * 100 if close is not None and ma20 else None,
            "pct",
        ),
    ]
    if (
        close is None
        or ma20 is None
        or close <= 0
        or ma20 <= 0
        or return_20d is None
        or breadth is None
        or not _valid_percentage(breadth)
        or not _breadth_coverage(row, "ma20EligibleCount")
    ):
        return _unavailable_layer(
            "trend_20d", "20日趋势", 20, metrics, "指数或MA20宽度数据不足，未判定趋势。"
        )
    if close > ma20 and return_20d > 0 and breadth > 50:
        classification: Literal["strong", "weak", "mixed"] = "strong"
        note = "指数位于MA20上方、20日收益为正，且多数合格股票位于MA20上方。"
    elif close < ma20 and return_20d < 0 and breadth < 50:
        classification = "weak"
        note = "指数位于MA20下方、20日收益为负，且多数合格股票位于MA20下方。"
    else:
        classification = "mixed"
        note = "指数位置、20日收益与个股MA20宽度至少一项不一致。"
    return MarketStateLayerRead(
        key="trend_20d",
        label="20日趋势",
        window_days=20,
        status="available",
        classification=classification,
        metrics=metrics,
        note=note,
    )


def _structure_layer(row: dict[str, Any]) -> MarketStateLayerRead:
    close = _decimal(row, "csi300Close")
    ma20 = _decimal(row, "csi300Ma20")
    ma60 = _decimal(row, "csi300Ma60")
    breadth = _decimal(row, "aboveMa60RatioPct")
    metrics = [
        _metric(
            "csi300_vs_ma60_pct",
            "沪深300相对MA60",
            (close / ma60 - 1) * 100 if close is not None and ma60 else None,
            "pct",
        ),
        _metric("above_ma60_ratio_pct", "MA60上方宽度", breadth, "pct"),
        _metric(
            "csi300_ma20_vs_ma60_pct",
            "沪深300 MA20相对MA60",
            (ma20 / ma60 - 1) * 100 if ma20 is not None and ma60 else None,
            "pct",
        ),
    ]
    if (
        close is None
        or ma20 is None
        or ma60 is None
        or close <= 0
        or ma20 <= 0
        or ma60 <= 0
        or breadth is None
        or not _valid_percentage(breadth)
        or not _breadth_coverage(row, "ma60EligibleCount")
    ):
        return _unavailable_layer(
            "structure_60d", "60日结构", 60, metrics, "指数或MA60宽度数据不足，未判定结构。"
        )
    if close > ma60 and ma20 > ma60 and breadth > 50:
        classification: Literal["strong", "weak", "conflicted"] = "strong"
        note = "指数与MA20均位于MA60上方，且多数合格股票位于MA60上方。"
    elif close < ma60 and ma20 < ma60 and breadth < 50:
        classification = "weak"
        note = "指数与MA20均位于MA60下方，且多数合格股票位于MA60下方。"
    else:
        classification = "conflicted"
        note = "指数、均线关系与个股MA60宽度存在分歧。"
    return MarketStateLayerRead(
        key="structure_60d",
        label="60日结构",
        window_days=60,
        status="available",
        classification=classification,
        metrics=metrics,
        note=note,
    )


def _facts(row: dict[str, Any]) -> MarketStateFactsRead:
    advancers = _int(row, "advancers")
    observed = _int(row, "returnObservedCount")
    return MarketStateFactsRead(
        csi300_return_1d_pct=_decimal(row, "csi300Return1dPct"),
        advancer_ratio_pct=(
            Decimal(advancers) / Decimal(observed) * 100
            if advancers is not None and observed
            else None
        ),
        median_return_pct=_decimal(row, "medianReturnPct"),
        above_ma20_ratio_pct=_decimal(row, "aboveMa20RatioPct"),
        above_ma60_ratio_pct=_decimal(row, "aboveMa60RatioPct"),
        amount_ratio_20=_decimal(row, "amountRatio20"),
        amount_rolling_120_midrank=_decimal(row, "amountRolling120Midrank"),
        csi300_volatility_20_pct=_decimal(row, "csi300Volatility20Pct"),
        csi300_drawdown_60_pct=_decimal(row, "csi300Drawdown60Pct"),
        limit_up_close_count=_int(row, "limitUpCloseCount"),
        limit_down_close_count=_int(row, "limitDownCloseCount"),
        broken_board_rate_pct=_decimal(row, "brokenBoardRatePct"),
        yesterday_limit_up_feedback_avg_return_pct=_decimal(
            row, "yesterdayLimitUpFeedbackAvgReturnPct"
        ),
        yesterday_limit_up_feedback_win_rate_pct=_decimal(
            row, "yesterdayLimitUpFeedbackWinRatePct"
        ),
    )


def _quality_issues(
    row: dict[str, Any],
    base: dict[str, Any] | None,
    short: MarketStateLayerRead,
    trend: MarketStateLayerRead,
    structure: MarketStateLayerRead,
) -> list[MarketStateIssueRead]:
    issues = [
        MarketStateIssueRead(
            code="exploratory_certification",
            message="事实层为EXPLORATORY；计算通过不等于ST、IPO特殊规则和历史可见性已完整认证。",
        )
    ]
    if base is None:
        issues.append(
            MarketStateIssueRead(
                code="history_insufficient_5d",
                message="没有第五个此前市场交易日，5日变化不可评估。",
            )
        )
    elif short.status == "unavailable":
        issues.append(
            MarketStateIssueRead(
                code="breadth_gate_failed_5d",
                message="5日端点存在宽度覆盖不足或数据缺失。",
            )
        )
    if trend.status == "unavailable":
        issues.append(
            MarketStateIssueRead(
                code="breadth_gate_failed_20d",
                message="20日趋势所需指数或MA20宽度覆盖不足。",
            )
        )
    if structure.status == "unavailable":
        issues.append(
            MarketStateIssueRead(
                code="breadth_gate_failed_60d",
                message="60日结构所需指数或MA60宽度覆盖不足。",
            )
        )
    bar_count = _int(row, "barCount")
    amount_coverage = _int(row, "amountCoverageCount")
    if (
        bar_count is None
        or amount_coverage is None
        or bar_count <= 0
        or Decimal(amount_coverage) / Decimal(bar_count) < MIN_AMOUNT_COVERAGE
    ):
        issues.append(
            MarketStateIssueRead(
                code="amount_coverage_below_95",
                message="成交额字段覆盖低于95%，成交活跃度只能作为不完整描述。",
            )
        )
    known = _int(row, "limitRuleKnownBarCount")
    if bar_count is not None and known is not None and known < bar_count:
        issues.append(
            MarketStateIssueRead(
                code="limit_rule_coverage_incomplete",
                message="部分bar涨跌停规则未知，涨停生态计数保持探索性。",
            )
        )
    return issues


def _conflicts(
    row: dict[str, Any],
    facts: MarketStateFactsRead,
    short: MarketStateLayerRead,
    trend: MarketStateLayerRead,
    structure: MarketStateLayerRead,
) -> list[MarketStateConflictRead]:
    conflicts: list[MarketStateConflictRead] = []
    if (
        facts.csi300_return_1d_pct is not None
        and facts.csi300_return_1d_pct > 0
        and (
            (facts.advancer_ratio_pct is not None and facts.advancer_ratio_pct < 50)
            or (facts.median_return_pct is not None and facts.median_return_pct < 0)
        )
    ):
        conflicts.append(
            MarketStateConflictRead(
                code="index_up_breadth_down",
                message="指数当日上涨，但上涨家数占比或个股收益中位数未达到多数。",
            )
        )
    if (
        short.classification == "weakening"
        and trend.classification == "strong"
        or short.classification == "improving"
        and trend.classification == "weak"
    ):
        conflicts.append(
            MarketStateConflictRead(
                code="short_trend_disagreement",
                message="5日变化方向与20日趋势相反，短期变化尚不足以改写趋势状态。",
            )
        )
    if (
        trend.classification == "strong"
        and structure.classification == "weak"
        or trend.classification == "weak"
        and structure.classification == "strong"
    ):
        conflicts.append(
            MarketStateConflictRead(
                code="trend_structure_disagreement",
                message="20日趋势与60日结构相反。",
            )
        )
    if (
        facts.yesterday_limit_up_feedback_avg_return_pct is not None
        and facts.yesterday_limit_up_feedback_avg_return_pct > 0
        and facts.above_ma20_ratio_pct is not None
        and _valid_percentage(facts.above_ma20_ratio_pct)
        and facts.above_ma20_ratio_pct < 50
        and _breadth_coverage(row, "ma20EligibleCount")
        and _feedback_observed(row)
    ):
        conflicts.append(
            MarketStateConflictRead(
                code="limit_feedback_positive_breadth_weak",
                message="昨日涨停股反馈为正，但全市场MA20宽度仍弱，存在局部与整体分歧。",
            )
        )
    return conflicts


def _summary(
    row: dict[str, Any],
    facts: MarketStateFactsRead,
    short: MarketStateLayerRead,
    trend: MarketStateLayerRead,
    structure: MarketStateLayerRead,
) -> str:
    short_labels = {
        "improving": "改善",
        "weakening": "恶化",
        "mixed": "分歧",
        "unavailable": "不可评估",
    }
    trend_labels = {
        "strong": "偏强",
        "weak": "偏弱",
        "mixed": "分歧",
        "unavailable": "不可评估",
    }
    structure_labels = {
        "strong": "偏强",
        "weak": "偏弱",
        "conflicted": "分歧",
        "unavailable": "不可评估",
    }
    parts = [
        f"5日变化{short_labels[short.classification]}",
        f"20日趋势{trend_labels[trend.classification]}",
        f"60日结构{structure_labels[structure.classification]}",
    ]
    text = "，".join(parts) + "。"
    if (
        facts.csi300_return_1d_pct is not None
        and facts.csi300_return_1d_pct > 0
        and facts.median_return_pct is not None
        and facts.median_return_pct < 0
    ):
        text += "当日指数上涨但个股收益中位数为负。"
    if (
        facts.amount_ratio_20 is not None
        and facts.amount_ratio_20 > 0
        and _amount_coverage(row)
        and facts.amount_ratio_20 < Decimal("0.8")
    ):
        text += "成交额低于此前20日均值。"
    elif (
        facts.amount_ratio_20 is not None
        and facts.amount_ratio_20 > 0
        and _amount_coverage(row)
        and facts.amount_ratio_20 > Decimal("1.2")
    ):
        text += "成交额高于此前20日均值。"
    if (
        facts.yesterday_limit_up_feedback_avg_return_pct is not None
        and facts.yesterday_limit_up_feedback_avg_return_pct > 0
        and facts.above_ma20_ratio_pct is not None
        and _valid_percentage(facts.above_ma20_ratio_pct)
        and facts.above_ma20_ratio_pct < 50
        and _breadth_coverage(row, "ma20EligibleCount")
        and _feedback_observed(row)
    ):
        text += "昨日涨停反馈为正，但全市场宽度仍弱。"
    return text


def _breadth_coverage(row: dict[str, Any], eligible_key: str) -> bool:
    bar_count = _int(row, "barCount")
    eligible = _int(row, eligible_key)
    return (
        bar_count is not None
        and eligible is not None
        and bar_count > 0
        and Decimal(eligible) / Decimal(bar_count) >= MIN_BREADTH_COVERAGE
    )


def _amount_coverage(row: dict[str, Any]) -> bool:
    return _coverage(row, "amountCoverageCount") >= MIN_AMOUNT_COVERAGE


def _coverage(row: dict[str, Any], count_key: str) -> Decimal:
    bar_count = _int(row, "barCount")
    count = _int(row, count_key)
    if bar_count is None or count is None or bar_count <= 0:
        return Decimal(0)
    return Decimal(count) / Decimal(bar_count)


def _feedback_observed(row: dict[str, Any]) -> bool:
    observed = _int(row, "yesterdayLimitUpFeedbackObservedCount")
    return observed is not None and observed > 0


def _valid_percentage(value: Decimal) -> bool:
    return Decimal(0) <= value <= Decimal(100)


def _scan_layer(values: list[str]) -> dict[str, Any]:
    counts = Counter(values)
    runs: list[int] = []
    current = None
    length = 0
    for value in values:
        if value == current:
            length += 1
        else:
            if current is not None:
                runs.append(length)
            current = value
            length = 1
    if current is not None:
        runs.append(length)
    ordered_runs = sorted(runs)
    return {
        "counts": dict(sorted(counts.items())),
        "shares_pct": {
            key: round(value * 100 / len(values), 4) for key, value in sorted(counts.items())
        },
        "runs": len(runs),
        "transitions": max(0, len(runs) - 1),
        "median_run_days": median(ordered_runs) if ordered_runs else None,
        "max_run_days": max(ordered_runs) if ordered_runs else None,
    }


def _metric(
    key: str,
    label: str,
    value: Decimal | None,
    unit: Literal["pct", "pp"],
) -> MarketStateLayerMetricRead:
    return MarketStateLayerMetricRead(key=key, label=label, value=value, unit=unit)


def _unavailable_layer(
    key: Literal["trend_20d", "structure_60d"],
    label: str,
    window_days: int,
    metrics: list[MarketStateLayerMetricRead],
    note: str,
) -> MarketStateLayerRead:
    return MarketStateLayerRead(
        key=key,
        label=label,
        window_days=window_days,
        status="unavailable",
        classification="unavailable",
        metrics=metrics,
        note=note,
    )


def _decimal(row: dict[str, Any] | None, key: str) -> Decimal | None:
    if row is None:
        return None
    value = row.get(key)
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _int(row: dict[str, Any], key: str) -> int | None:
    value = row.get(key)
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, float) and not value.is_integer():
            return None
        parsed = int(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return parsed
