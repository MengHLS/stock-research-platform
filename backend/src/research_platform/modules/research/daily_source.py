"""SELECT-only adapter for READY first-board events and causal price history."""

from __future__ import annotations

import json
import re
from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import Engine, bindparam, text
from sqlalchemy.exc import SQLAlchemyError

from research_platform.core.errors import DomainError

from .first_board_features import HistoricalBar


@dataclass(frozen=True)
class DailyInput:
    trading_day: date
    dataset_version_id: str
    source_version: str
    universe_definition: str
    calendar: list[date]
    events: dict[str, str]
    bars: dict[str, dict[date, HistoricalBar]]


class SqlFirstBoardSource:
    def __init__(self, engine: Engine):
        self.engine = engine

    def load(self, cutoff: date) -> DailyInput:
        try:
            with self.engine.connect() as connection:
                return self._load(connection, cutoff)
        except SQLAlchemyError:
            raise DomainError("FIRST_BOARD_SOURCE_UNAVAILABLE") from None
        except (ValueError, TypeError, KeyError, InvalidOperation):
            raise DomainError("FIRST_BOARD_SOURCE_BAD_DATA") from None

    def _load(self, connection, cutoff: date) -> DailyInput:
        def query(sql, params=None, *, symbols=False):
            statement = text(sql)
            if symbols:
                statement = statement.bindparams(bindparam("symbols", expanding=True))
            return connection.execute(statement, params or {}).mappings().all()

        days = query(
            """SELECT DISTINCT tradeDate FROM index_daily
               WHERE indexCode = '000001.SH' AND tradeDate <= :cutoff
               ORDER BY tradeDate DESC LIMIT 62""",
            {"cutoff": cutoff.isoformat()},
        )
        if not days:
            raise DomainError("FIRST_BOARD_DATE_UNAVAILABLE")
        trading_day = _date(days[0]["tradeDate"])
        calendar = sorted(_date(row["tradeDate"]) for row in days[1:])
        versions = query(
            """SELECT v.id, v.version, v.universeDefinitionJson, v.filterDefinitionJson
               FROM dataset_version v JOIN dataset_definition d ON d.id = v.datasetId
               WHERE d.datasetCode = 'first_limit_pullback' AND d.status = 'ACTIVE'
                 AND v.status = 'READY' AND v.startDate <= :day AND v.endDate >= :day
               ORDER BY v.id DESC""",
            {"day": trading_day.isoformat()},
        )
        version = None
        for candidate in versions:
            filters = json.loads(candidate["filterDefinitionJson"])
            if not isinstance(filters, dict) or not isinstance(filters.get("events"), list):
                raise ValueError("Invalid event filter definition")
            if not all(isinstance(item, dict) for item in filters["events"]):
                raise ValueError("Invalid event filter")
            if any(item.get("kind") == "firstBoard" for item in filters["events"]):
                version = candidate
                break
        if version is None:
            raise DomainError("FIRST_BOARD_DATE_UNAVAILABLE")
        universe_value = json.loads(version["universeDefinitionJson"])
        if not isinstance(universe_value, dict):
            raise ValueError("Invalid universe")
        universe = json.dumps(universe_value, sort_keys=True, separators=(",", ":"))
        rows = query(
            """SELECT eventId, symbol, tradeDate, isFirstLimit
               FROM ds_first_limit_pullback_event
               WHERE datasetVersionId = :version AND tradeDate = :day
               ORDER BY symbol, eventId""",
            {"version": version["id"], "day": trading_day.isoformat()},
        )
        events: dict[str, str] = {}
        for row in rows:
            symbol = row["symbol"]
            if (
                not re.fullmatch(r"\d{6}\.(SH|SZ|BJ)", symbol)
                or row["isFirstLimit"] != 1
                or _date(row["tradeDate"]) != trading_day
                or row["eventId"] != f"{symbol}@{trading_day.isoformat()}"
                or symbol in events
            ):
                raise ValueError("Invalid or duplicate first-board event")
            events[symbol] = row["eventId"]
        bars: dict[str, dict[date, HistoricalBar]] = {symbol: {} for symbol in events}
        if events and calendar:
            params = {
                "symbols": list(events),
                "start": calendar[0].isoformat(),
                "end": calendar[-1].isoformat(),
            }
            prices = query(
                """SELECT stockCode, tradeDate, openPrice, highPrice, lowPrice, closePrice
                   FROM stock_daily_prices
                   WHERE stockCode IN :symbols AND tradeDate >= :start AND tradeDate <= :end
                   ORDER BY stockCode, tradeDate""",
                params,
                symbols=True,
            )
            factors = query(
                """SELECT securityCode, effectiveDate, backFactor FROM adjustment_factors
                   WHERE securityCode IN :symbols AND effectiveDate <= :end
                   ORDER BY securityCode, effectiveDate""",
                params,
                symbols=True,
            )
            actions = query(
                """SELECT securityCode, effectiveDate FROM corporate_actions
                   WHERE securityCode IN :symbols AND effectiveDate <= :end
                   ORDER BY securityCode, effectiveDate""",
                params,
                symbols=True,
            )
            factor_map: dict[str, dict[date, Decimal | None]] = {s: {} for s in events}
            action_map: dict[str, set[date]] = {s: set() for s in events}
            for row in factors:
                mapping = factor_map[row["securityCode"]]
                day = _date(row["effectiveDate"])
                if day in mapping:
                    raise ValueError("Duplicate adjustment factor")
                mapping[day] = _decimal(row["backFactor"])
            for row in actions:
                action_map[row["securityCode"]].add(_date(row["effectiveDate"]))
            factor_dates = {s: sorted(mapping) for s, mapping in factor_map.items()}
            action_dates = {s: sorted(days) for s, days in action_map.items()}
            for row in prices:
                symbol, day = row["stockCode"], _date(row["tradeDate"])
                if day in bars[symbol]:
                    raise ValueError("Duplicate price")
                factor = visible_factor(
                    day, factor_dates[symbol], factor_map[symbol], action_dates[symbol]
                )
                bars[symbol][day] = HistoricalBar(
                    day,
                    _decimal(row["openPrice"]),
                    _decimal(row["highPrice"]),
                    _decimal(row["lowPrice"]),
                    _decimal(row["closePrice"]),
                    factor,
                )
        return DailyInput(
            trading_day, str(version["id"]), version["version"], universe, calendar, events, bars
        )


def visible_factor(day, factor_dates, factors, action_dates):
    """Never backfill from a future factor or carry across an unaccounted action."""
    position = bisect_right(factor_dates, day) - 1
    if position < 0:
        return None
    past_values = [factors[effective] for effective in factor_dates[: position + 1]]
    if any(value is None or value <= 0 for value in past_values):
        return None
    if any(first > second for first, second in zip(past_values, past_values[1:], strict=False)):
        return None
    effective = factor_dates[position]
    latest_action = bisect_right(action_dates, day) - 1
    if latest_action >= 0 and action_dates[latest_action] > effective:
        return None
    return factors[effective]


def _date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else date.fromisoformat(value)


def _decimal(value) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("Non-finite price or factor")
    return number
