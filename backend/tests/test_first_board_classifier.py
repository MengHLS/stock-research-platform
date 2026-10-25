from decimal import Decimal

import pytest

from research_platform.modules.research import first_board_classifier as classifier
from research_platform.modules.research import service


def axes(code: str):
    cases = {
        "FBC-01": (Decimal("75"), classifier.Trend.UP, classifier.ShortPath.UP_PULLBACK),
        "FBC-02": (Decimal("35"), classifier.Trend.UP, classifier.ShortPath.UP_PULLBACK),
        "FBC-03": (Decimal("20"), classifier.Trend.DOWN, classifier.ShortPath.DOWN_CONTINUATION),
        "FBC-04": (Decimal("50"), classifier.Trend.DOWN, classifier.ShortPath.DOWN_CONTINUATION),
        "FBC-05": (Decimal("20"), classifier.Trend.DOWN, classifier.ShortPath.DOWN_REBOUND),
        "FBC-06": (Decimal("50"), classifier.Trend.DOWN, classifier.ShortPath.DOWN_REBOUND),
        "FBC-07": (None, classifier.Trend.SIDEWAYS, classifier.ShortPath.NEUTRAL),
        "FBC-08": (Decimal("50"), classifier.Trend.SIDEWAYS, classifier.ShortPath.UP_CONTINUATION),
        "FBC-09": (Decimal("50"), classifier.Trend.SIDEWAYS, classifier.ShortPath.UP_PULLBACK),
        "FBC-10": (
            Decimal("50"),
            classifier.Trend.SIDEWAYS,
            classifier.ShortPath.DOWN_CONTINUATION,
        ),
        "FBC-11": (Decimal("50"), classifier.Trend.SIDEWAYS, classifier.ShortPath.DOWN_REBOUND),
        "FBC-12": (Decimal("75"), classifier.Trend.UP, classifier.ShortPath.UP_CONTINUATION),
        "FBC-13": (Decimal("50"), classifier.Trend.UP, classifier.ShortPath.UP_CONTINUATION),
        "FBC-14": (Decimal("50"), classifier.Trend.UP, classifier.ShortPath.NEUTRAL),
        "FBC-15": (Decimal("50"), classifier.Trend.DOWN, classifier.ShortPath.NEUTRAL),
        "FBC-16": (None, classifier.Trend.UNKNOWN, classifier.ShortPath.UP_PULLBACK),
    }
    return cases[code]


def test_catalog_is_a_complete_renumbered_view_of_the_sixteen_detail_classes():
    result = service.catalog()

    assert result.class_count == 16
    assert result.group_count == 7
    assert [len(group.class_codes) for group in result.groups] == [2, 2, 2, 5, 2, 2, 1]
    assert len({item.code for item in result.classes}) == 16
    assert len({item.source_detail_code for item in result.classes}) == 16
    assert [item.source_detail_code for item in result.classes] == [
        "G1-H",
        "G1-ML",
        "G2-L",
        "G2-M",
        "G3-L",
        "G3-M",
        "G4-N",
        "G4-UC",
        "G4-PB",
        "G4-DC",
        "G4-RB",
        "G5-H",
        "G5-ML",
        "R1-UP",
        "R1-DN",
        "U1-U",
    ]
    assert result.low_position_max_pct == Decimal("35")
    assert result.high_position_min_pct == Decimal("75")


@pytest.mark.parametrize("expected_code", [f"FBC-{number:02d}" for number in range(1, 17)])
def test_every_detail_class_has_one_deterministic_new_code(expected_code):
    result = classifier.classify(*axes(expected_code))

    assert result.definition.code == expected_code
    assert result.group.code == result.definition.group_code


def test_position_boundaries_are_inclusive_and_use_decimal_thresholds():
    assert classifier.position_band(Decimal("0")) is classifier.PositionBand.LOW
    assert classifier.position_band(Decimal("35")) is classifier.PositionBand.LOW
    assert classifier.position_band(Decimal("35.0001")) is classifier.PositionBand.MID
    assert classifier.position_band(Decimal("74.9999")) is classifier.PositionBand.MID
    assert classifier.position_band(Decimal("75")) is classifier.PositionBand.HIGH
    assert classifier.position_band(Decimal("100")) is classifier.PositionBand.HIGH


def test_unknown_trend_or_path_is_explicitly_retained_as_information_insufficient():
    unknown_trend = classifier.classify(
        None,
        classifier.Trend.UNKNOWN,
        classifier.ShortPath.DOWN_REBOUND,
    )
    unknown_path = classifier.classify(
        Decimal("80"),
        classifier.Trend.UP,
        classifier.ShortPath.UNKNOWN,
    )

    assert unknown_trend.definition.code == "FBC-16"
    assert unknown_path.definition.code == "FBC-16"


@pytest.mark.parametrize(
    ("position", "trend", "short_path"),
    [
        (Decimal("50"), classifier.Trend.UP, classifier.ShortPath.DOWN_REBOUND),
        (Decimal("50"), classifier.Trend.DOWN, classifier.ShortPath.UP_CONTINUATION),
        (None, classifier.Trend.UP, classifier.ShortPath.UP_PULLBACK),
        (Decimal("80"), classifier.Trend.DOWN, classifier.ShortPath.DOWN_CONTINUATION),
    ],
)
def test_known_but_unsupported_axes_do_not_fall_into_another_class(
    position,
    trend,
    short_path,
):
    with pytest.raises(classifier.UnsupportedAxisCombination):
        classifier.classify(position, trend, short_path)


def test_classifier_api_catalog_classification_and_unsupported_combo(client_factory):
    client = client_factory(1)

    catalog = client.get("/api/v1/research/first-board-classifier")
    assert catalog.status_code == 200
    assert catalog.json()["class_count"] == 16
    assert catalog.json()["classes"][0]["source_detail_code"] == "G1-H"

    classified = client.post(
        "/api/v1/research/first-board-classifier/classify",
        json={
            "position_60d_pct": "80",
            "trend": "up",
            "short_path": "up_pullback",
        },
    )
    assert classified.status_code == 200
    payload = classified.json()
    assert payload["class_code"] == "FBC-01"
    assert payload["group_code"] == "FBG-01"
    assert payload["source_detail_code"] == "G1-H"
    assert payload["classification_cutoff"] == "T-1"
    assert payload["input_time_assurance"] == "caller_declared"
    assert payload["uses_forward_data"] is False

    unsupported = client.post(
        "/api/v1/research/first-board-classifier/classify",
        json={
            "position_60d_pct": "80",
            "trend": "down",
            "short_path": "up_continuation",
        },
    )
    assert unsupported.status_code == 422
    assert unsupported.json()["detail"]["code"] == "FIRST_BOARD_CLASSIFICATION_UNSUPPORTED"


def test_classifier_requires_authentication_and_rejects_extra_fields(client_factory):
    assert client_factory().get("/api/v1/research/first-board-classifier").status_code == 503

    client = client_factory(1)
    invalid = client.post(
        "/api/v1/research/first-board-classifier/classify",
        json={
            "position_60d_pct": "80",
            "trend": "up",
            "short_path": "up_pullback",
            "group": "G1",
        },
    )
    assert invalid.status_code == 422
