"""Read-only, verified access to the frozen detail-class event ledger."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import re
import threading
import zlib
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from research_platform.core.errors import DomainError

from . import first_board_classifier as classifier

DEFAULT_EXPECTED_EVENTS = 73_003
DEFAULT_SOURCE_SHA256 = "e8c0e19aa1e26c21252bde6202f689c28b1eb02555861e7eb8e565d1b151c7bb"
DEFAULT_LEDGER_SHA256 = "70794b8b9174755002950a3e73d565c287ffa4afcdbffa7667ed47ee984572d1"
REQUIRED_FIELDS = {
    "eventId",
    "stockCode",
    "eventDate",
    "extendedResearchGroup",
    "position60Pct",
    "position",
    "trend",
    "shortPath",
    "detailClass",
    "detailClassName",
}


class FirstBoardDatasetError(RuntimeError):
    """The frozen ledger is missing, changed, or inconsistent with its summary."""


class FirstBoardDatasetUnavailable(FirstBoardDatasetError):
    """A required ledger file cannot be read."""


@dataclass(frozen=True, slots=True)
class FirstBoardEvent:
    event_id: str
    stock_code: str
    event_date: date
    position_60d_pct: Decimal | None
    position_band: classifier.PositionBand
    trend: classifier.Trend
    short_path: classifier.ShortPath
    class_code: str
    class_name: str
    group_code: str
    group_name: str
    source_detail_code: str
    source_group_code: str


@dataclass(frozen=True, slots=True)
class FirstBoardDataset:
    events: tuple[FirstBoardEvent, ...]
    by_stock: dict[str, tuple[FirstBoardEvent, ...]]
    dataset_version_id: int
    source_task_id: str
    source_sha256: str
    ledger_sha256: str
    class_counts: dict[str, int]


class FrozenFirstBoardDatasetSource:
    """Load and verify once, then serve compact read-only event records."""

    def __init__(
        self,
        root: Path,
        expected_events: int = DEFAULT_EXPECTED_EVENTS,
        expected_source_sha256: str = DEFAULT_SOURCE_SHA256,
        expected_ledger_sha256: str = DEFAULT_LEDGER_SHA256,
    ) -> None:
        self._root = Path(root)
        self._expected_events = expected_events
        self._expected_source_sha256 = expected_source_sha256
        self._expected_ledger_sha256 = expected_ledger_sha256
        self._dataset: FirstBoardDataset | None = None
        self._lock = threading.Lock()

    def load(self) -> FirstBoardDataset:
        with self._lock:
            if self._dataset is None:
                self._dataset = self._load()
            return self._dataset

    def _load(self) -> FirstBoardDataset:
        summary = _read_object(self._root / "summary.json")
        verification = _read_object(self._root / "verification.json")
        sources = summary.get("sources")
        outputs = summary.get("outputs")
        if not isinstance(sources, dict) or not isinstance(outputs, dict):
            raise FirstBoardDatasetError("summary source/output metadata is invalid")
        if (
            verification.get("status") != "PASS"
            or verification.get("mismatchCount") != 0
            or verification.get("classes") != len(classifier.CLASSES)
            or verification.get("derivedEvents") != self._expected_events
            or verification.get("sourceEvents") != self._expected_events
            or verification.get("sourceSha256") != sources.get("fullUniverseSha256")
        ):
            raise FirstBoardDatasetError("source verification is not a matching PASS")
        if (
            sources.get("fullUniverseSha256") != self._expected_source_sha256
            or outputs.get("eventDetailClassesSha256") != self._expected_ledger_sha256
        ):
            raise FirstBoardDatasetError("source hashes differ from the trusted baseline")
        if summary.get("taskId") != "FIRSTBOARD-DETAIL-CLASSES-V1-20261025":
            raise FirstBoardDatasetError("unsupported source taxonomy")
        if summary.get("status") != "COMPLETE":
            raise FirstBoardDatasetError("summary status is not COMPLETE")
        if summary.get("classificationChange") is not False:
            raise FirstBoardDatasetError("source reports a classification change")
        if summary.get("newFeatures") is not False:
            raise FirstBoardDatasetError("source reports new features")
        if summary.get("eventRows") != self._expected_events:
            raise FirstBoardDatasetError("event row count differs from the frozen count")
        if summary.get("sourceEvents") != self._expected_events:
            raise FirstBoardDatasetError("source event count differs from the frozen count")
        if summary.get("summaryRows") != len(classifier.CLASSES):
            raise FirstBoardDatasetError("source class count differs from the taxonomy")
        source_task_id = summary.get("sourceTaskId")
        dataset_version_id = summary.get("datasetVersionId")
        if source_task_id != "FIRSTBOARD-FULL-UNIVERSE-V1-20261025" or dataset_version_id != 660001:
            raise FirstBoardDatasetError("source identity metadata differs from the baseline")
        expected_hash = outputs.get("eventDetailClassesSha256")
        if not isinstance(expected_hash, str) or len(expected_hash) != 64:
            raise FirstBoardDatasetError("summary does not declare the event ledger hash")

        ledger_path = self._root / "event-detail-classes.csv.gz"
        actual_hash = _digest(ledger_path)
        if (
            actual_hash != expected_hash
            or actual_hash != verification.get("derivedSha256")
            or actual_hash != self._expected_ledger_sha256
        ):
            raise FirstBoardDatasetError("event ledger hash differs from summary")

        events = _read_events(ledger_path)
        if len(events) != self._expected_events:
            raise FirstBoardDatasetError("event ledger row count differs from summary")
        if len({item.event_id for item in events}) != len(events):
            raise FirstBoardDatasetError("event ledger contains duplicate event IDs")
        if len({(item.stock_code, item.event_date) for item in events}) != len(events):
            raise FirstBoardDatasetError("event ledger contains duplicate stock-date identities")

        counts = Counter(item.source_detail_code for item in events)
        frozen_counts = summary.get("classCounts")
        canonical_classes = set(classifier.SOURCE_DETAIL_CLASS_TO_CODE)
        if (
            not isinstance(frozen_counts, dict)
            or set(frozen_counts) != canonical_classes
            or set(counts) != canonical_classes
        ):
            raise FirstBoardDatasetError("event classes differ from summary keys")
        if any(counts[code] != frozen_counts[code] for code in counts):
            raise FirstBoardDatasetError("event class counts differ from summary")
        group_counts = summary.get("groupCounts")
        canonical_groups = {item.source_group_code for item in classifier.GROUPS}
        if (
            not isinstance(group_counts, dict)
            or set(group_counts) != canonical_groups
            or dict(Counter(item.source_group_code for item in events)) != group_counts
        ):
            raise FirstBoardDatasetError("event group counts differ from summary")

        by_stock_lists: dict[str, list[FirstBoardEvent]] = {}
        for item in events:
            by_stock_lists.setdefault(item.stock_code, []).append(item)
        by_stock = {
            stock: tuple(sorted(rows, key=lambda row: (row.event_date, row.event_id)))
            for stock, rows in by_stock_lists.items()
        }
        new_counts = Counter(item.class_code for item in events)
        return FirstBoardDataset(
            events=events,
            by_stock=by_stock,
            dataset_version_id=dataset_version_id,
            source_task_id=source_task_id,
            source_sha256=self._expected_source_sha256,
            ledger_sha256=actual_hash,
            class_counts=dict(new_counts),
        )


def source_or_error(
    source: FrozenFirstBoardDatasetSource | None,
) -> FirstBoardDataset:
    if source is None:
        raise DomainError("SOURCE_NOT_CONFIGURED")
    try:
        return source.load()
    except (OSError, FirstBoardDatasetUnavailable):
        raise DomainError("FIRST_BOARD_DATASET_UNAVAILABLE") from None
    except (
        ValueError,
        InvalidOperation,
        EOFError,
        csv.Error,
        zlib.error,
        FirstBoardDatasetError,
    ):
        raise DomainError("FIRST_BOARD_DATASET_BAD_DATA") from None


def _read_events(path: Path) -> tuple[FirstBoardEvent, ...]:
    records: list[FirstBoardEvent] = []
    try:
        with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or not REQUIRED_FIELDS.issubset(reader.fieldnames):
                raise FirstBoardDatasetError("event ledger header is incomplete")
            for row in reader:
                records.append(_parse_event(row))
    except (gzip.BadGzipFile, zlib.error) as error:
        raise FirstBoardDatasetError("event ledger cannot be decoded") from error
    return tuple(records)


def _parse_event(row: dict[str, str]) -> FirstBoardEvent:
    source_detail_code = _required(row, "detailClass")
    class_code = classifier.SOURCE_DETAIL_CLASS_TO_CODE.get(source_detail_code)
    if class_code is None:
        raise FirstBoardDatasetError("event ledger contains an unknown detail class")
    definition = classifier.CLASSES_BY_CODE[class_code]
    group = classifier.GROUPS_BY_CODE[definition.group_code]

    position_text = _required(row, "position60Pct", allow_empty=True)
    position = Decimal(position_text) if position_text else None
    band = _enum(classifier.PositionBand, _required(row, "position"))
    if position is not None:
        # The legacy floating-point export can contain 100.00000000000001.
        # Preserve that source value; only normalize roundoff for validation.
        if not position.is_finite() or not Decimal("-1e-10") <= position <= Decimal(
            "100.0000000001"
        ):
            raise FirstBoardDatasetError("event ledger contains an invalid relative position")
        bounded = min(Decimal("100"), max(Decimal("0"), position))
        if classifier.position_band(bounded) != band:
            raise FirstBoardDatasetError("event ledger position label disagrees with the feature")
    elif band is not classifier.PositionBand.UNKNOWN:
        raise FirstBoardDatasetError("event ledger position feature is missing")
    result = classifier.classify_labels(
        band,
        _enum(classifier.Trend, _required(row, "trend")),
        _enum(classifier.ShortPath, _required(row, "shortPath")),
    )
    if result.definition.code != class_code:
        raise FirstBoardDatasetError("event ledger class disagrees with the frozen axes")
    if _required(row, "extendedResearchGroup") != group.source_group_code:
        raise FirstBoardDatasetError("event ledger group disagrees with the detail class")

    event_date = date.fromisoformat(_required(row, "eventDate"))
    stock_code = _required(row, "stockCode")
    if re.fullmatch(r"\d{6}\.(?:SH|SZ|BJ)", stock_code) is None:
        raise FirstBoardDatasetError("event ledger contains an invalid stock code")
    event_id = _required(row, "eventId")
    if event_id != f"{stock_code}@{event_date.isoformat()}":
        raise FirstBoardDatasetError("event identity disagrees with stock and date")
    return FirstBoardEvent(
        event_id=event_id,
        stock_code=stock_code,
        event_date=event_date,
        position_60d_pct=position,
        position_band=band,
        trend=result.trend,
        short_path=result.short_path,
        class_code=definition.code,
        class_name=definition.name,
        group_code=group.code,
        group_name=group.name,
        source_detail_code=definition.source_detail_code,
        source_group_code=group.source_group_code,
    )


def _enum(enum_type, value: str):
    try:
        return enum_type(value.lower())
    except ValueError:
        raise FirstBoardDatasetError("event ledger contains an unknown axis value") from None


def _required(row: dict[str, str], field: str, *, allow_empty: bool = False) -> str:
    value = row.get(field)
    if value is None or (not allow_empty and not value.strip()):
        raise FirstBoardDatasetError(f"event ledger field is empty: {field}")
    return value.strip()


def _read_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FirstBoardDatasetUnavailable(f"file is missing: {path.name}")
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise FirstBoardDatasetError(f"JSON object required: {path.name}")
    return value


def _digest(path: Path) -> str:
    if not path.is_file():
        raise FirstBoardDatasetUnavailable(f"file is missing: {path.name}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
