from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from research_platform.core.cache import TTLCache
from research_platform.core.errors import DomainError
from research_platform.modules.market.global_types import GlobalBar
from research_platform.modules.market.models import ReviewIndexDailyBar
from research_platform.modules.market.review import PUBLIC_INDEX_SYMBOLS, IndexBar
from research_platform.modules.market.review_index_store import SqlReviewIndexStore
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


def index_bar(day: str, close: str) -> IndexBar:
    value = Decimal(close)
    return IndexBar(
        trading_day=date.fromisoformat(day),
        symbol="399006.SZ",
        open=value - 5,
        high=value + 10,
        low=value - 10,
        close=value,
        amount_source=None,
        volume_source=None,
    )


def test_public_index_source_filters_to_the_review_range_and_uses_160_bar_window(store):
    client = MagicMock()
    client.history.return_value = [
        bar("2026-02-23", "3900"),
        bar("2026-02-24", "3910"),
        bar("2026-02-27", "3920"),
        bar("2026-03-03", "3930"),
    ]
    source = PublicReviewIndexSource(client, store, cache_seconds=60)

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


def test_public_index_source_returns_no_latest_bar_for_a_date_before_its_coverage(store):
    client = MagicMock()
    client.history.return_value = [
        bar("2026-02-24", "3910"),
        bar("2026-02-25", "3920"),
    ]
    source = PublicReviewIndexSource(client, store)

    rows = source.index_rows(
        date(2026, 1, 5),
        date(2026, 1, 6),
        ["000688.SH"],
    )["000688.SH"]

    assert rows == []


def test_public_index_source_reuses_the_cached_history_between_review_endpoints(store):
    client = MagicMock()
    client.history.return_value = [bar("2026-10-20", "4000")]
    source = PublicReviewIndexSource(client, store, cache_seconds=60)

    source.index_rows(date(2026, 10, 20), date(2026, 10, 20), ["399006.SZ"])
    source.index_rows(date(2026, 10, 19), date(2026, 10, 20), ["399006.SZ"])

    assert client.history.call_count == 1


def test_public_index_source_rejects_unreviewed_symbols(store):
    source = PublicReviewIndexSource(MagicMock(), store)

    with pytest.raises(ValueError, match="unsupported public review index"):
        source.index_rows(date(2026, 10, 20), date(2026, 10, 20), ["000001.SH"])


def test_public_index_mapping_matches_the_reviewed_symbol_order():
    assert tuple(PUBLIC_REVIEW_INDEX_INSTRUMENTS) == PUBLIC_INDEX_SYMBOLS


@pytest.fixture
def store(database_url):
    engine = create_engine(database_url)
    yield SqlReviewIndexStore(sessionmaker(engine, expire_on_commit=False))
    engine.dispose()


def test_persisted_rows_survive_new_source_and_failed_refresh(store):
    client = MagicMock()
    client.history.return_value = [bar("2026-10-19", "3900"), bar("2026-10-20", "4000")]
    now = datetime(2026, 10, 20, 8)
    first = PublicReviewIndexSource(client, store, now=lambda: now)
    first.index_rows(date(2026, 10, 19), date(2026, 10, 20), ["399006.SZ"])
    assert store.latest_fetched_at("399006.SZ") == now

    offline = MagicMock()
    offline.history.side_effect = DomainError("MARKET_SOURCE_UNAVAILABLE")
    second = PublicReviewIndexSource(offline, store, now=lambda: now + timedelta(hours=2))
    rows = second.index_rows(date(2026, 10, 19), date(2026, 10, 19), ["399006.SZ"])
    assert [row.close for row in rows["399006.SZ"]] == [Decimal("3900")]
    assert offline.history.call_count == 1
    assert store.latest_fetched_at("399006.SZ") == now


def test_refresh_is_idempotent_and_preserves_history_outside_latest_window(store):
    client = MagicMock()
    client.history.side_effect = [
        [bar("2026-10-19", "3900"), bar("2026-10-20", "4000")],
        [bar("2026-10-20", "4010")],
    ]
    source = PublicReviewIndexSource(client, store, cache_seconds=0, refresh_seconds=0)
    for _ in range(2):
        source.index_rows(date(2026, 10, 19), date(2026, 10, 20), ["399006.SZ"])
    rows = store.index_rows(date(2026, 10, 19), date(2026, 10, 20), ["399006.SZ"])
    assert [row.close for row in rows["399006.SZ"]] == [Decimal("3900"), Decimal("4010")]
    with store._sessions() as session:
        assert session.scalar(select(func.count()).select_from(ReviewIndexDailyBar)) == 2
        row = session.get(ReviewIndexDailyBar, ("399006.SZ", date(2026, 10, 20)))
        assert row.provider == "tencent"
        assert row.fetched_at is not None


def test_older_refresh_cannot_overwrite_newer_persisted_values(store):
    newer = datetime(2026, 10, 20, 9)
    older = newer - timedelta(hours=1)
    store.upsert(
        "399006.SZ",
        [index_bar("2026-10-20", "4010")],
        provider="tencent",
        fetched_at=newer,
    )
    SqlReviewIndexStore(store._sessions).upsert(
        "399006.SZ",
        [index_bar("2026-10-20", "3990")],
        provider="tencent",
        fetched_at=older,
    )

    rows = store.index_rows(
        date(2026, 10, 20),
        date(2026, 10, 20),
        ["399006.SZ"],
    )["399006.SZ"]
    assert rows[0].close == Decimal("4010")
    assert store.latest_fetched_at("399006.SZ") == newer


def test_expired_refresh_fetches_upstream_instead_of_relabelling_cached_history(store):
    client = MagicMock()
    client.history.side_effect = [
        [bar("2026-10-20", "4000")],
        [bar("2026-10-20", "4010")],
    ]
    clock = [0.0]
    cache = TTLCache(clock=lambda: clock[0])
    now = [datetime(2026, 10, 20, 8)]
    source = PublicReviewIndexSource(
        client,
        store,
        cache=cache,
        cache_seconds=3600,
        refresh_seconds=1,
        now=lambda: now[0],
    )

    source.index_rows(date(2026, 10, 20), date(2026, 10, 20), ["399006.SZ"])
    clock[0] = 2
    now[0] += timedelta(seconds=2)
    source.index_rows(date(2026, 10, 20), date(2026, 10, 20), ["399006.SZ"])

    rows = store.index_rows(
        date(2026, 10, 20),
        date(2026, 10, 20),
        ["399006.SZ"],
    )["399006.SZ"]
    assert client.history.call_count == 2
    assert rows[0].close == Decimal("4010")
    assert store.latest_fetched_at("399006.SZ") == now[0]


def test_single_symbol_failure_is_retried_without_hiding_other_symbol(store):
    client = MagicMock()
    client.history.side_effect = [
        DomainError("MARKET_SOURCE_UNAVAILABLE"),
        [bar("2026-10-20", "1300")],
        [bar("2026-10-20", "4000")],
    ]
    source = PublicReviewIndexSource(client, store)
    first = source.index_rows(date(2026, 10, 20), date(2026, 10, 20), list(PUBLIC_INDEX_SYMBOLS))
    assert first["399006.SZ"] == []
    assert first["000688.SH"][0].close == Decimal("1300")
    second = source.index_rows(date(2026, 10, 20), date(2026, 10, 20), ["399006.SZ"])
    assert second["399006.SZ"][0].close == Decimal("4000")
    assert client.history.call_count == 3
