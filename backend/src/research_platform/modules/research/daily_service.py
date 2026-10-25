"""Refresh READY events using only T-1 history, then publish a complete snapshot."""

import hashlib
import json
from collections import Counter
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta, timezone

from research_platform.core.errors import DomainError

from .daily_source import SqlFirstBoardSource
from .daily_store import SqlFirstBoardStore
from .first_board_classifier import (
    CLASSES_BY_CODE,
    TAXONOMY_VERSION,
    UnsupportedAxisCombination,
    classify,
)
from .first_board_features import FEATURE_VERSION, compute_background_features
from .schemas import FirstBoardDailyRead, StoredFirstBoardEventRead


class FirstBoardDailyService:
    def __init__(self, source: SqlFirstBoardSource | None, store: SqlFirstBoardStore):
        self.source = source
        self.store = store

    def refresh(self, as_of: date | None = None, *, now: datetime | None = None):
        if self.source is None:
            raise DomainError("SOURCE_NOT_CONFIGURED")
        current = (now or datetime.now(UTC)).astimezone(timezone(timedelta(hours=8)))
        cutoff = current.date()
        if (current.hour, current.minute) < (15, 30):
            cutoff -= timedelta(days=1)
        if as_of is not None:
            if as_of > cutoff:
                raise DomainError("FIRST_BOARD_DATE_NOT_CLOSED")
            cutoff = as_of
        source = self.source.load(cutoff)
        if source.trading_day > cutoff or any(day >= source.trading_day for day in source.calendar):
            raise DomainError("FIRST_BOARD_SOURCE_BAD_DATA")
        inputs = {
            "day": source.trading_day,
            "dataset": source.dataset_version_id,
            "source_version": source.source_version,
            "universe": source.universe_definition,
            "calendar": source.calendar,
            "events": sorted(source.events.items()),
            "bars": [
                (symbol, [asdict(bar) for _, bar in sorted(bars.items())])
                for symbol, bars in sorted(source.bars.items())
            ],
            "taxonomy": TAXONOMY_VERSION,
            "features": FEATURE_VERSION,
        }
        batch_id = hashlib.sha256(
            json.dumps(inputs, sort_keys=True, default=str, separators=(",", ":")).encode()
        ).hexdigest()
        events = []
        for symbol, event_id in sorted(source.events.items()):
            features = compute_background_features(source.calendar, source.bars.get(symbol, {}))
            class_code = group_code = None
            reason = features.feature_reason
            try:
                result = classify(features.position_60d_pct, features.trend, features.short_path)
                class_code, group_code = result.definition.code, result.group.code
            except UnsupportedAxisCombination:
                reason = ";".join(filter(None, [reason, "UNSUPPORTED_AXIS_COMBINATION"]))
            events.append(
                {
                    "batch_id": batch_id,
                    "event_id": event_id,
                    "stock_code": symbol,
                    "trading_day": source.trading_day,
                    "feature_cutoff": source.calendar[-1] if source.calendar else None,
                    "class_code": class_code,
                    "group_code": group_code,
                    **asdict(features),
                    "feature_reason": reason,
                }
            )
        self.store.publish(
            {
                "batch_id": batch_id,
                "trading_day": source.trading_day,
                "dataset_version_id": source.dataset_version_id,
                "source_version": source.source_version,
                "universe_definition": source.universe_definition,
                "taxonomy_version": TAXONOMY_VERSION,
                "feature_version": FEATURE_VERSION,
                "source_event_count": len(source.events),
                "computed_at": datetime.now(UTC).replace(tzinfo=None),
            },
            events,
        )
        return self.daily(source.trading_day, limit=500, batch_id=batch_id)

    def daily(self, day: date | None = None, *, offset=0, limit=100, batch_id=None):
        batch, events = self.store.read(day, TAXONOMY_VERSION, FEATURE_VERSION, batch_id=batch_id)
        if batch is None:
            return FirstBoardDailyRead(
                trading_day=day,
                status="NOT_REFRESHED",
                total=0,
                offset=offset,
                limit=limit,
                taxonomy_version=TAXONOMY_VERSION,
                feature_version=FEATURE_VERSION,
            )
        unsupported = sum(row.class_code is None for row in events)
        quality_counts = dict(Counter(row.quality_status for row in events))
        status = (
            "EMPTY"
            if not events
            else (
                "COMPLETE"
                if quality_counts.get("COMPLETE") == len(events) and not unsupported
                else "PARTIAL"
            )
        )
        items = []
        for row in events[offset : offset + limit]:
            item = StoredFirstBoardEventRead.model_validate(row)
            item.class_name = CLASSES_BY_CODE[row.class_code].name if row.class_code else None
            items.append(item)
        return FirstBoardDailyRead(
            trading_day=batch.trading_day,
            status=status,
            batch_id=batch.batch_id,
            dataset_version_id=batch.dataset_version_id,
            source_version=batch.source_version,
            universe_definition=batch.universe_definition,
            taxonomy_version=batch.taxonomy_version,
            feature_version=batch.feature_version,
            computed_at=batch.computed_at.replace(tzinfo=UTC),
            source_event_count=batch.source_event_count,
            total=len(events),
            offset=offset,
            limit=limit,
            class_counts=dict(
                sorted(Counter(row.class_code for row in events if row.class_code).items())
            ),
            quality_counts=quality_counts,
            unsupported_count=unsupported,
            items=items,
        )
