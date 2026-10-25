"""Application service for the deterministic first-board classifier."""

from __future__ import annotations

from datetime import date

from research_platform.core.errors import DomainError

from . import first_board_classifier as classifier
from .daily_service import FirstBoardDailyService
from .dataset_source import (
    FrozenFirstBoardDatasetSource,
    source_or_error,
)
from .schemas import (
    ClassificationRead,
    ClassificationRequest,
    ClassifierCatalogRead,
    ClassRead,
    DatasetSourceRead,
    FirstBoardEventListRead,
    FirstBoardEventRead,
    FirstBoardHistoryEventRead,
    FirstBoardHistoryRead,
    FirstBoardHistorySourceRead,
    GroupRead,
)

_POSITION_LABELS = {
    classifier.PositionBand.LOW: "60日低位",
    classifier.PositionBand.MID: "60日中位",
    classifier.PositionBand.HIGH: "60日高位",
    classifier.PositionBand.UNKNOWN: "60日位置未知",
}
_TREND_LABELS = {
    classifier.Trend.UP: "上升趋势",
    classifier.Trend.DOWN: "下降趋势",
    classifier.Trend.SIDEWAYS: "整体方向未明确",
    classifier.Trend.UNKNOWN: "趋势未知",
}
_PATH_LABELS = {
    classifier.ShortPath.UP_CONTINUATION: "短期向上延续",
    classifier.ShortPath.UP_PULLBACK: "短期上升回调",
    classifier.ShortPath.DOWN_CONTINUATION: "短期向下延续",
    classifier.ShortPath.DOWN_REBOUND: "短期下降反弹",
    classifier.ShortPath.NEUTRAL: "短期中性",
    classifier.ShortPath.UNKNOWN: "短期路径未知",
}


def catalog() -> ClassifierCatalogRead:
    classes = [
        ClassRead(
            code=item.code,
            name=item.name,
            group_code=item.group_code,
            group_name=classifier.GROUPS_BY_CODE[item.group_code].name,
            source_detail_code=item.source_detail_code,
            source_group_code=item.source_group_code,
            condition=item.condition,
            position_scope=item.position_scope,
            trend=item.trend,
            short_path=item.short_path,
        )
        for item in classifier.CLASSES
    ]
    groups = [
        GroupRead(
            code=group.code,
            name=group.name,
            source_group_code=group.source_group_code,
            description=group.description,
            class_codes=[item.code for item in classifier.CLASSES if item.group_code == group.code],
        )
        for group in classifier.GROUPS
    ]
    return ClassifierCatalogRead(
        class_count=len(classes),
        group_count=len(groups),
        low_position_max_pct=classifier.LOW_POSITION_MAX_PCT,
        high_position_min_pct=classifier.HIGH_POSITION_MIN_PCT,
        groups=groups,
        classes=classes,
        notes=[
            "分类只使用截至 T-1 的 60 日相对位置、趋势和短期路径；首板事件在 T 日收盘确认。",
            "名称中的“背景”只描述事件发生前的状态，不预示后续收益、结构或交易结果。",
            "整体方向未明确沿用原 SIDEWAYS 残差状态，不等于已经确认横盘箱体。",
            "信息不足不是股票质量评价；未知值不填补为零或其他类别。",
            "新旧编码通过 source_detail_code 追溯，判定条件保持不变。",
        ],
    )


def classify(data: ClassificationRequest) -> ClassificationRead:
    try:
        result = classifier.classify(
            data.position_60d_pct,
            data.trend,
            data.short_path,
        )
    except classifier.UnsupportedAxisCombination as error:
        raise DomainError("FIRST_BOARD_CLASSIFICATION_UNSUPPORTED") from error

    explanation = (
        f"{_POSITION_LABELS[result.position]}；"
        f"{_TREND_LABELS[result.trend]}，{_PATH_LABELS[result.short_path]}。"
        f"归入 {result.definition.code} {result.definition.name}；"
        "仅描述截至 T-1 的背景，不使用 T 日后的数据。"
    )
    return ClassificationRead(
        class_code=result.definition.code,
        class_name=result.definition.name,
        group_code=result.group.code,
        group_name=result.group.name,
        source_detail_code=result.definition.source_detail_code,
        position_60d_pct=data.position_60d_pct,
        position_band=result.position,
        trend=result.trend,
        short_path=result.short_path,
        explanation=explanation,
    )


def events(
    source: FrozenFirstBoardDatasetSource | None,
    stock_code: str,
    event_date: date | None,
    limit: int,
) -> FirstBoardEventListRead:
    dataset = source_or_error(source)
    if "." in stock_code:
        rows = dataset.by_stock.get(stock_code, ())
    else:
        rows = tuple(
            item
            for suffix in ("SH", "SZ", "BJ")
            for item in dataset.by_stock.get(f"{stock_code}.{suffix}", ())
        )
        rows = tuple(sorted(rows, key=lambda item: (item.event_date, item.event_id)))
    if event_date is not None:
        rows = tuple(item for item in rows if item.event_date == event_date)
    items = [
        FirstBoardEventRead(
            event_id=item.event_id,
            stock_code=item.stock_code,
            event_date=item.event_date,
            class_code=item.class_code,
            class_name=item.class_name,
            group_code=item.group_code,
            group_name=item.group_name,
            source_detail_code=item.source_detail_code,
            source_group_code=item.source_group_code,
            position_60d_pct=item.position_60d_pct,
            position_band=item.position_band,
            trend=item.trend,
            short_path=item.short_path,
        )
        for item in rows[:limit]
    ]
    return FirstBoardEventListRead(
        stock_code=stock_code,
        event_date=event_date,
        items=items,
        total=len(rows),
        limit=limit,
        source=DatasetSourceRead(
            dataset_version_id=dataset.dataset_version_id,
            source_task_id=dataset.source_task_id,
            source_sha256=dataset.source_sha256,
            ledger_sha256=dataset.ledger_sha256,
            event_count=len(dataset.events),
        ),
    )


def stock_history(
    source: FrozenFirstBoardDatasetSource | None,
    daily: FirstBoardDailyService,
    stock_code: str,
    limit: int,
) -> FirstBoardHistoryRead:
    """Merge verified frozen history with the current persisted daily snapshots."""
    symbols = (
        (stock_code,)
        if "." in stock_code
        else tuple(f"{stock_code}.{suffix}" for suffix in ("SH", "SZ", "BJ"))
    )
    frozen_status = "NOT_CONFIGURED"
    frozen_dataset_version_id = None
    frozen_event_count = None
    frozen_rows = []
    if source is not None:
        try:
            dataset = source_or_error(source)
        except DomainError:
            frozen_status = "BAD_DATA"
        else:
            frozen_status = "PASS"
            frozen_dataset_version_id = dataset.dataset_version_id
            frozen_event_count = len(dataset.events)
            frozen_rows = [
                FirstBoardHistoryEventRead(
                    event_id=item.event_id,
                    stock_code=item.stock_code,
                    event_date=item.event_date,
                    class_code=item.class_code,
                    class_name=item.class_name,
                    group_code=item.group_code,
                    group_name=item.group_name,
                    source_detail_code=item.source_detail_code,
                    source_group_code=item.source_group_code,
                    position_60d_pct=item.position_60d_pct,
                    position_band=item.position_band,
                    trend=item.trend,
                    short_path=item.short_path,
                    quality_status=("INSUFFICIENT" if item.class_code == "FBC-16" else "COMPLETE"),
                    source_kind="frozen",
                    data_version="first-board-background-v1",
                )
                for symbol in symbols
                for item in dataset.by_stock.get(symbol, ())
            ]

    stored_models = [row for symbol in symbols for row in daily.stored_for_stock(symbol)]
    stored_rows = []
    for row in stored_models:
        definition = (
            classifier.CLASSES_BY_CODE.get(row.class_code) if row.class_code is not None else None
        )
        stored_rows.append(
            FirstBoardHistoryEventRead(
                event_id=row.event_id,
                stock_code=row.stock_code,
                event_date=row.trading_day,
                class_code=row.class_code,
                class_name=definition.name if definition else None,
                group_code=row.group_code,
                group_name=(
                    classifier.GROUPS_BY_CODE[definition.group_code].name if definition else None
                ),
                source_detail_code=definition.source_detail_code if definition else None,
                source_group_code=definition.source_group_code if definition else None,
                position_60d_pct=row.position_60d_pct,
                position_band=row.position_band,
                trend=row.trend,
                short_path=row.short_path,
                quality_status=row.quality_status,
                feature_reason=row.feature_reason,
                source_kind="stored",
                data_version="stored-daily-first-board-v1",
            )
        )

    merged = {item.event_id: item for item in frozen_rows}
    merged.update((item.event_id, item) for item in stored_rows)
    ordered = sorted(
        merged.values(),
        key=lambda item: (item.event_date, item.event_id),
        reverse=True,
    )
    return FirstBoardHistoryRead(
        stock_code=stock_code,
        items=ordered[:limit],
        total=len(ordered),
        limit=limit,
        source=FirstBoardHistorySourceRead(
            frozen_status=frozen_status,
            frozen_dataset_version_id=frozen_dataset_version_id,
            frozen_event_count=frozen_event_count,
            stored_batch_count=len({item.batch_id for item in stored_models}),
            stored_event_count=len(stored_rows),
        ),
    )
