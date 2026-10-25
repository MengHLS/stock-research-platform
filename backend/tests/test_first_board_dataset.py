import csv
import gzip
import hashlib
import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from research_platform.core.config import FirstBoardDatasetConfig, Settings
from research_platform.main import create_app
from research_platform.modules.identity.dependencies import Actor, require_actor
from research_platform.modules.research import first_board_classifier as classifier
from research_platform.modules.research.dataset_source import (
    FirstBoardDatasetError,
    FrozenFirstBoardDatasetSource,
)

SOURCE_HASH = "a" * 64
EVENT_COUNT = len(classifier.CLASSES)
FIELDS = (
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
)


def write_delivery(root: Path, *, summary_mutator=None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    base = date(2019, 9, 1)
    for index, definition in enumerate(classifier.CLASSES):
        event_date = (base + timedelta(days=index)).isoformat()
        position, position_value = {
            "high": ("HIGH", "82.4"),
            "mid_or_low": ("MID", "50"),
            "low": ("LOW", "20"),
            "mid": ("MID", "50"),
            "any": ("MID", "50"),
        }[definition.position_scope]
        if definition.code == "FBC-16":
            position, position_value = "UNKNOWN", ""
            trend, short_path = "UNKNOWN", "DOWN_CONTINUATION"
        else:
            trend = definition.trend.value.upper()
            short_path = definition.short_path.value.upper()
        rows.append(
            {
                "eventId": f"603121.SH@{event_date}",
                "stockCode": "603121.SH",
                "eventDate": event_date,
                "extendedResearchGroup": definition.source_group_code,
                "position60Pct": position_value,
                "position": position,
                "trend": trend,
                "shortPath": short_path,
                "detailClass": definition.source_detail_code,
                "detailClassName": definition.source_detail_code,
            }
        )
    ledger = root / "event-detail-classes.csv.gz"
    with gzip.open(ledger, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    digest = hashlib.sha256(ledger.read_bytes()).hexdigest()
    summary = {
        "taskId": "FIRSTBOARD-DETAIL-CLASSES-V1-20261025",
        "status": "COMPLETE",
        "classificationChange": False,
        "newFeatures": False,
        "eventRows": EVENT_COUNT,
        "sourceEvents": EVENT_COUNT,
        "summaryRows": 16,
        "sourceTaskId": "FIRSTBOARD-FULL-UNIVERSE-V1-20261025",
        "datasetVersionId": 660001,
        "classCounts": dict(Counter(row["detailClass"] for row in rows)),
        "groupCounts": dict(Counter(row["extendedResearchGroup"] for row in rows)),
        "outputs": {"eventDetailClassesSha256": digest},
        "sources": {"fullUniverseSha256": SOURCE_HASH},
    }
    if summary_mutator:
        summary_mutator(summary)
    (root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False),
        encoding="utf-8",
    )
    (root / "verification.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "mismatchCount": 0,
                "classes": 16,
                "derivedEvents": EVENT_COUNT,
                "sourceEvents": EVENT_COUNT,
                "derivedSha256": digest,
                "sourceSha256": SOURCE_HASH,
            }
        ),
        encoding="utf-8",
    )
    return root


def test_frozen_source_verifies_hash_counts_and_new_class_mapping(tmp_path):
    source = FrozenFirstBoardDatasetSource(
        write_delivery(tmp_path),
        expected_events=EVENT_COUNT,
        expected_source_sha256=SOURCE_HASH,
        expected_ledger_sha256=hashlib.sha256(
            (tmp_path / "event-detail-classes.csv.gz").read_bytes()
        ).hexdigest(),
    )

    dataset = source.load()

    assert dataset.dataset_version_id == 660001
    assert dataset.source_task_id == "FIRSTBOARD-FULL-UNIVERSE-V1-20261025"
    assert dataset.source_sha256 == SOURCE_HASH
    assert (
        dataset.ledger_sha256
        == hashlib.sha256((tmp_path / "event-detail-classes.csv.gz").read_bytes()).hexdigest()
    )
    assert dataset.class_counts == {item.code: 1 for item in classifier.CLASSES}
    assert len(dataset.by_stock["603121.SH"]) == EVENT_COUNT
    assert dataset.by_stock["603121.SH"][0].class_code == "FBC-01"
    assert dataset.by_stock["603121.SH"][-1].class_code == "FBC-16"


def test_frozen_source_rejects_changed_ledger_or_taxonomy_mismatch(tmp_path):
    root = write_delivery(tmp_path)
    (root / "event-detail-classes.csv.gz").write_bytes(b"changed")
    with pytest.raises(FirstBoardDatasetError, match="hash"):
        FrozenFirstBoardDatasetSource(
            root,
            expected_events=EVENT_COUNT,
            expected_source_sha256=SOURCE_HASH,
            expected_ledger_sha256="b" * 64,
        ).load()

    other = write_delivery(
        tmp_path / "other",
        summary_mutator=lambda summary: summary.update(newFeatures=True),
    )
    with pytest.raises(FirstBoardDatasetError, match="features"):
        FrozenFirstBoardDatasetSource(
            other,
            expected_events=EVENT_COUNT,
            expected_source_sha256=SOURCE_HASH,
            expected_ledger_sha256=hashlib.sha256(
                (other / "event-detail-classes.csv.gz").read_bytes()
            ).hexdigest(),
        ).load()


def test_frozen_source_rejects_event_identity_mismatch_even_with_internal_hashes(tmp_path):
    root = write_delivery(tmp_path)
    with gzip.open(root / "event-detail-classes.csv.gz", "rt", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    rows[0]["stockCode"] = "999999.SH"
    with gzip.open(root / "event-detail-classes.csv.gz", "wt", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    digest = hashlib.sha256((root / "event-detail-classes.csv.gz").read_bytes()).hexdigest()
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    summary["outputs"]["eventDetailClassesSha256"] = digest
    (root / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    verification = json.loads((root / "verification.json").read_text(encoding="utf-8"))
    verification["derivedSha256"] = digest
    (root / "verification.json").write_text(json.dumps(verification), encoding="utf-8")

    with pytest.raises(FirstBoardDatasetError, match="event identity"):
        FrozenFirstBoardDatasetSource(
            root,
            expected_events=EVENT_COUNT,
            expected_source_sha256=SOURCE_HASH,
            expected_ledger_sha256=digest,
        ).load()


def test_frozen_source_maps_malformed_metadata_and_compression_to_bad_data(tmp_path):
    root = write_delivery(tmp_path)
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    summary["outputs"] = None
    (root / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises(FirstBoardDatasetError, match="metadata"):
        FrozenFirstBoardDatasetSource(
            root,
            expected_events=EVENT_COUNT,
            expected_source_sha256=SOURCE_HASH,
            expected_ledger_sha256=hashlib.sha256(
                (root / "event-detail-classes.csv.gz").read_bytes()
            ).hexdigest(),
        ).load()

    corrupted = write_delivery(tmp_path / "corrupted")
    (corrupted / "event-detail-classes.csv.gz").write_bytes(b"not-gzip")
    digest = hashlib.sha256(b"not-gzip").hexdigest()
    summary = json.loads((corrupted / "summary.json").read_text(encoding="utf-8"))
    summary["outputs"]["eventDetailClassesSha256"] = digest
    (corrupted / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    verification = json.loads((corrupted / "verification.json").read_text(encoding="utf-8"))
    verification["derivedSha256"] = digest
    (corrupted / "verification.json").write_text(json.dumps(verification), encoding="utf-8")
    with pytest.raises(FirstBoardDatasetError, match="decoded"):
        FrozenFirstBoardDatasetSource(
            corrupted,
            expected_events=EVENT_COUNT,
            expected_source_sha256=SOURCE_HASH,
            expected_ledger_sha256=digest,
        ).load()


def test_event_api_returns_real_frozen_records_with_new_codes(database_url):
    root = write_delivery(Path(database_url.removeprefix("sqlite:///")).parent / "first-board")
    settings = Settings(
        environment="test",
        database_url=database_url,
        first_board_dataset=FirstBoardDatasetConfig(root=root),
        _env_file=None,
    )
    app = create_app(settings)
    app.state.first_board_dataset = FrozenFirstBoardDatasetSource(
        root,
        expected_events=EVENT_COUNT,
        expected_source_sha256=SOURCE_HASH,
        expected_ledger_sha256=hashlib.sha256(
            (root / "event-detail-classes.csv.gz").read_bytes()
        ).hexdigest(),
    )
    app.dependency_overrides[require_actor] = lambda: Actor(user_id=1)

    with TestClient(app) as client:
        assert (
            "502"
            in app.openapi()["paths"]["/api/v1/research/first-board-classifier/events"]["get"][
                "responses"
            ]
        )
        response = client.get(
            "/api/v1/research/first-board-classifier/events",
            params={"stock_code": "603121", "limit": 20},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == EVENT_COUNT
        assert payload["source"]["verification_status"] == "pass"
        assert payload["items"][0]["class_code"] == "FBC-01"
        assert payload["items"][-1]["class_code"] == "FBC-16"
        assert payload["items"][0]["source_detail_code"] == "G1-H"

        exact = client.get(
            "/api/v1/research/first-board-classifier/events",
            params={"stock_code": "603121", "date": "2019-09-16"},
        )
        assert exact.status_code == 200
        assert exact.json()["total"] == 1
        assert exact.json()["items"][0]["class_code"] == "FBC-16"

        invalid = client.get(
            "/api/v1/research/first-board-classifier/events",
            params={"stock_code": "ABC"},
        )
        assert invalid.status_code == 422
