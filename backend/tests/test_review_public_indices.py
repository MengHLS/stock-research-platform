from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from research_platform.modules.market.global_types import GlobalBar
from research_platform.modules.market.review import PUBLIC_INDEX_SYMBOLS
from research_platform.modules.market.review_public_indices import (
    PUBLIC_REVIEW_INDEX_INSTRUMENTS,
    PublicReviewIndexSource,
)


def bar(day: str, close: str) -> GlobalBar:
    value = Decimal(close)
    return GlobalBar(
        trading_day=date.fromisoformat(day),
        open=value - 5,
        high=value + 10,
        low=value - 10,
        close=value,
        change_pct=None,
    )


def test_public_index_source_filters_to_the_review_range_and_uses_160_bar_window():
    client = MagicMock()
    client.history.return_value = [
        bar("2026-02-23", "3900"),
        bar("2026-02-24", "3910"),
        bar("2026-02-27", "3920"),
        bar("2026-03-03", "3930"),
    ]
    source = PublicReviewIndexSource(client, cache_seconds=60)

    rows = source.index_rows(
        date(2026, 2, 24),
        date(2026, 3, 2),
        ["399006.SZ"],
    )["399006.SZ"]

    assert [item.trading_day for item in rows] == [
        date(2026, 2, 24),
        date(2026, 2, 27),
    ]
    assert rows[0].close == Decimal("3910")
    assert rows[0].amount_source is None
    assert rows[0].volume_source is None
    assert client.history.call_args.args[1] == 160
    assert client.history.call_args.args[0].tencent_symbol == "sz399006"


def test_public_index_source_returns_no_latest_bar_for_a_date_before_its_coverage():
    client = MagicMock()
    client.history.return_value = [
        bar("2026-02-24", "3910"),
        bar("2026-02-25", "3920"),
    ]
    source = PublicReviewIndexSource(client)

    rows = source.index_rows(
        date(2026, 1, 5),
        date(2026, 1, 6),
        ["000688.SH"],
    )["000688.SH"]

    assert rows == []


def test_public_index_source_reuses_the_cached_history_between_review_endpoints():
    client = MagicMock()
    client.history.return_value = [bar("2026-10-20", "4000")]
    source = PublicReviewIndexSource(client, cache_seconds=60)

    source.index_rows(date(2026, 10, 20), date(2026, 10, 20), ["399006.SZ"])
    source.index_rows(date(2026, 10, 19), date(2026, 10, 20), ["399006.SZ"])

    assert client.history.call_count == 1


def test_public_index_source_rejects_unreviewed_symbols():
    source = PublicReviewIndexSource(MagicMock())

    with pytest.raises(ValueError, match="unsupported public review index"):
        source.index_rows(date(2026, 10, 20), date(2026, 10, 20), ["000001.SH"])


def test_public_index_mapping_matches_the_reviewed_symbol_order():
    assert tuple(PUBLIC_REVIEW_INDEX_INSTRUMENTS) == PUBLIC_INDEX_SYMBOLS
