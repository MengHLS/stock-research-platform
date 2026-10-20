"""Read-only adapter for a verified market-state delivery directory."""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from research_platform.core.errors import DomainError


class MarketStateSourceError(RuntimeError):
    """The frozen delivery is missing, changed, or internally inconsistent."""


class MarketStateSourceUnavailable(MarketStateSourceError):
    """A required delivery file cannot be read."""


@dataclass(frozen=True)
class MarketStateTable:
    rows: tuple[dict[str, Any], ...]
    by_date: dict[str, dict[str, Any]]
    source_sha256: str
    universe_id: str
    feature_version: str
    build_version: str
    certification_level: str


class MarketStateSource(Protocol):
    def load(self) -> MarketStateTable: ...


class FrozenMarketStateSource:
    """Verify once, then serve the immutable table from memory."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._table: MarketStateTable | None = None
        self._lock = threading.Lock()

    def load(self) -> MarketStateTable:
        with self._lock:
            if self._table is None:
                self._table = self._load()
            return self._table

    def _load(self) -> MarketStateTable:
        root = self._root
        verification = _read_object(root / "verification.json")
        if verification.get("status") != "PASS":
            raise MarketStateSourceError("verification is not PASS")
        output_files = verification.get("outputFiles")
        if not isinstance(output_files, dict):
            raise MarketStateSourceError("verification outputFiles is missing")
        expected = output_files.get("market-state-daily.json")
        if not isinstance(expected, str) or len(expected) != 64:
            raise MarketStateSourceError("verification does not declare the daily JSON hash")
        table_path = root / "market-state-daily.json"
        table_bytes = _read_bytes(table_path)
        actual = hashlib.sha256(table_bytes).hexdigest()
        if actual != expected:
            raise MarketStateSourceError("daily JSON hash differs from verification")
        payload = _decode_object(table_bytes, table_path.name)
        rows = payload.get("rows")
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise MarketStateSourceError("daily JSON rows are invalid")
        row_count = payload.get("rowCount")
        if isinstance(row_count, bool) or not isinstance(row_count, int) or row_count != len(rows):
            raise MarketStateSourceError("daily JSON rowCount does not match rows")
        universe_id = payload.get("universeId")
        feature_version = payload.get("featureVersion")
        if (
            not isinstance(universe_id, str)
            or not universe_id
            or not isinstance(feature_version, str)
            or not feature_version
        ):
            raise MarketStateSourceError("daily JSON version metadata is missing")
        by_date: dict[str, dict[str, Any]] = {}
        previous = ""
        for row in rows:
            day = row.get("tradeDate")
            if not isinstance(day, str) or day in by_date or day <= previous:
                raise MarketStateSourceError("trade dates are duplicated or unsorted")
            try:
                parsed_day = date.fromisoformat(day)
            except ValueError:
                raise MarketStateSourceError("trade date is invalid") from None
            if parsed_day.isoformat() != day:
                raise MarketStateSourceError("trade dates are duplicated or unsorted")
            if row.get("universeId") != universe_id or row.get("featureVersion") != feature_version:
                raise MarketStateSourceError("row version metadata is inconsistent")
            by_date[day] = row
            previous = day
        meta_path = root / "run-meta.json"
        meta = _read_object(meta_path) if meta_path.is_file() else {}
        build_version = meta.get("buildVersion", "unknown")
        certification_level = meta.get("certificationLevel", "UNKNOWN")
        if not isinstance(build_version, str) or not isinstance(certification_level, str):
            raise MarketStateSourceError("run metadata is invalid")
        return MarketStateTable(
            rows=tuple(rows),
            by_date=by_date,
            source_sha256=actual,
            universe_id=universe_id,
            feature_version=feature_version,
            build_version=build_version,
            certification_level=certification_level,
        )


def source_or_error(source: MarketStateSource | None) -> MarketStateTable:
    if source is None:
        raise DomainError("SOURCE_NOT_CONFIGURED")
    try:
        return source.load()
    except (OSError, MarketStateSourceUnavailable):
        raise DomainError("MARKET_STATE_SOURCE_UNAVAILABLE") from None
    except (ValueError, json.JSONDecodeError, MarketStateSourceError):
        raise DomainError("MARKET_STATE_SOURCE_BAD_DATA") from None
    except DomainError:
        raise


def _read_object(path: Path) -> dict[str, Any]:
    return _decode_object(_read_bytes(path), path.name)


def _decode_object(raw: bytes, name: str) -> dict[str, Any]:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise MarketStateSourceError(f"JSON object required: {name}")
    return value


def _read_bytes(path: Path) -> bytes:
    if not path.is_file():
        raise MarketStateSourceUnavailable(f"file is missing: {path.name}")
    return path.read_bytes()
