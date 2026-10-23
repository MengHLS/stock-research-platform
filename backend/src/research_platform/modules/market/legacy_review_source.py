"""Read-only adapter from reviewed legacy tables to the market-review seam."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import TypeVar

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from research_platform.core.errors import DomainError
from research_platform.core.logging import log_event

from .review import (
    IndexBar,
    LimitUpRecord,
    MarketWideRow,
    ReviewDateCoverage,
    ReviewSourceDataError,
    StockBar,
    StockQuote,
)
from .review_counts import DailyBar, SecurityMetadata

T = TypeVar("T")


class LegacyMarketReviewSource:
    """SELECT-only mapping for the legacy review database.

    The application ORM is deliberately not bound to these tables. Schema and
    migration ownership remain with the legacy system; this adapter only reads
    the columns reviewed by the market-review contract.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def trading_days(self, start: date, end: date) -> list[date]:
        def load() -> list[date]:
            rows = self._query(
                """
                SELECT DISTINCT tradeDate
                FROM index_daily
                WHERE tradeDate >= :start AND tradeDate <= :end
                ORDER BY tradeDate
                """,
                {"start": start.isoformat(), "end": end.isoformat()},
            )
            return sorted({_date(row["tradeDate"]) for row in rows})

        return self._safe(load, "trading_days")

    def calendar_bounds(self, end: date) -> tuple[date | None, date | None]:
        def load() -> tuple[date | None, date | None]:
            rows = self._query(
                """
                SELECT MIN(tradeDate) AS first_day, MAX(tradeDate) AS last_day
                FROM index_daily WHERE tradeDate <= :end
                """,
                {"end": end.isoformat()},
            )
            row = rows[0] if rows else {}
            return (_optional_date(row.get("first_day")), _optional_date(row.get("last_day")))

        return self._safe(load, "calendar_bounds")

    def latest_trading_day(self, end: date) -> date | None:
        def load() -> date | None:
            rows = self._query(
                "SELECT MAX(tradeDate) AS last_day FROM index_daily WHERE tradeDate <= :end",
                {"end": end.isoformat()},
            )
            return _optional_date(rows[0].get("last_day") if rows else None)

        return self._safe(load, "latest_trading_day")

    def latest_limit_up_date(self, end: date) -> date | None:
        def load() -> date | None:
            rows = self._query(
                """
                SELECT MAX(limitUpDate) AS last_day
                FROM limit_up_records
                WHERE limitUpDate <= :end
                """,
                {"end": end.isoformat()},
            )
            return _optional_date(rows[0].get("last_day") if rows else None)

        return self._safe(load, "latest_limit_up_date")

    def latest_review_date(self, end: date) -> date | None:
        def load() -> date | None:
            rows = self._query(
                """
                SELECT MAX(l.limitUpDate) AS last_day
                FROM limit_up_records l
                WHERE l.limitUpDate <= :end
                  AND EXISTS (
                    SELECT 1 FROM index_daily i WHERE i.tradeDate = l.limitUpDate
                  )
                """,
                {"end": end.isoformat()},
            )
            return _optional_date(rows[0].get("last_day") if rows else None)

        return self._safe(load, "latest_review_date")

    def trading_day_neighbours(
        self, trading_day: date, end: date
    ) -> tuple[date | None, date | None]:
        def load() -> tuple[date | None, date | None]:
            previous_rows = self._query(
                """
                SELECT MAX(tradeDate) AS day
                FROM index_daily
                WHERE tradeDate < :day AND tradeDate <= :end
                """,
                {"day": trading_day.isoformat(), "end": end.isoformat()},
            )
            next_rows = self._query(
                """
                SELECT MIN(tradeDate) AS day
                FROM index_daily
                WHERE tradeDate > :day AND tradeDate <= :end
                """,
                {"day": trading_day.isoformat(), "end": end.isoformat()},
            )
            return (
                _optional_date(previous_rows[0].get("day") if previous_rows else None),
                _optional_date(next_rows[0].get("day") if next_rows else None),
            )

        return self._safe(load, "trading_day_neighbours")

    def daily_coverage(self, start: date, end: date) -> list[ReviewDateCoverage]:
        def load() -> list[ReviewDateCoverage]:
            index_rows = self._query(
                """
                SELECT tradeDate,
                       SUM(CASE WHEN indexCode = '000001.SH' THEN 1 ELSE 0 END) AS shanghai_rows,
                       SUM(CASE WHEN indexCode = '399001.SZ' THEN 1 ELSE 0 END) AS shenzhen_rows,
                       SUM(CASE WHEN indexCode = '000300.SH' THEN 1 ELSE 0 END) AS csi300_rows,
                       SUM(CASE WHEN indexCode = '000905.SH' THEN 1 ELSE 0 END) AS csi500_rows
                FROM index_daily
                WHERE tradeDate >= :start AND tradeDate <= :end
                GROUP BY tradeDate
                ORDER BY tradeDate
                """,
                {"start": start.isoformat(), "end": end.isoformat()},
            )
            limit_rows = self._query(
                """
                SELECT limitUpDate AS tradeDate, COUNT(DISTINCT stockCode) AS row_count
                FROM limit_up_records
                WHERE limitUpDate >= :start AND limitUpDate <= :end
                GROUP BY limitUpDate
                """,
                {"start": start.isoformat(), "end": end.isoformat()},
            )
            market_rows = self._query(
                """
                SELECT dataDate AS tradeDate, COUNT(*) AS row_count
                FROM market_data
                WHERE dataDate >= :start AND dataDate <= :end
                GROUP BY dataDate
                """,
                {"start": start.isoformat(), "end": end.isoformat()},
            )
            limit_counts = {_date(row["tradeDate"]): int(row["row_count"]) for row in limit_rows}
            market_counts = {_date(row["tradeDate"]): int(row["row_count"]) for row in market_rows}
            result: list[ReviewDateCoverage] = []
            for row in index_rows:
                day = _date(row["tradeDate"])
                result.append(
                    ReviewDateCoverage(
                        trading_day=day,
                        limit_up_rows=limit_counts.get(day, 0),
                        market_wide_rows=market_counts.get(day, 0),
                        shanghai_rows=_row_count(row["shanghai_rows"]),
                        shenzhen_rows=_row_count(row["shenzhen_rows"]),
                        csi300_rows=_row_count(row["csi300_rows"]),
                        csi500_rows=_row_count(row["csi500_rows"]),
                    )
                )
            return result

        return self._safe(load, "daily_coverage")

    def limit_up_records(self, start: date, end: date) -> list[LimitUpRecord]:
        def load() -> list[LimitUpRecord]:
            rows = self._query(
                """
                SELECT stockCode, stockName, limitUpDate, limitUpTime, sector
                FROM limit_up_records
                WHERE limitUpDate >= :start AND limitUpDate <= :end
                ORDER BY limitUpDate, stockCode, limitUpTime
                """,
                {"start": start.isoformat(), "end": end.isoformat()},
            )
            return [
                LimitUpRecord(
                    trading_day=_date(row["limitUpDate"]),
                    symbol=_text_required(row["stockCode"]),
                    name=_text_required(row["stockName"]),
                    sector=_text_optional(row["sector"]),
                    limit_up_time=_time_optional(row["limitUpTime"]),
                )
                for row in rows
            ]

        return self._safe(load, "limit_up_records")

    def stock_quotes(self, trading_day: date, symbols: list[str]) -> list[StockQuote]:
        return self.stock_quotes_range(trading_day, trading_day, symbols)

    def stock_quotes_range(
        self,
        start: date,
        end: date,
        symbols: list[str],
    ) -> list[StockQuote]:
        def load() -> list[StockQuote]:
            if not symbols:
                return []
            rows = self._query(
                """
                SELECT stockCode, tradeDate, openPrice, highPrice, lowPrice,
                       closePrice, preClosePrice
                FROM stock_daily_prices
                WHERE tradeDate >= :start AND tradeDate <= :end
                  AND stockCode IN :symbols
                ORDER BY tradeDate, stockCode
                """,
                {
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "symbols": symbols,
                },
                expanding=("symbols",),
            )
            result: list[StockQuote] = []
            for row in rows:
                open_price = _decimal_optional(row["openPrice"])
                high = _decimal_optional(row["highPrice"])
                low = _decimal_optional(row["lowPrice"])
                close = _decimal_optional(row["closePrice"])
                previous = _decimal_optional(row["preClosePrice"])
                change_pct = (
                    ((close - previous) / previous * 100)
                    if close is not None and previous is not None and previous != 0
                    else None
                )
                result.append(
                    StockQuote(
                        trading_day=_date(row["tradeDate"]),
                        symbol=_text_required(row["stockCode"]),
                        change_pct=change_pct,
                        one_word_board=(
                            open_price == high == low
                            and close is not None
                            and previous is not None
                            and close > previous
                            if (
                                open_price is not None
                                and high is not None
                                and low is not None
                                and close is not None
                                and previous is not None
                            )
                            else None
                        ),
                    )
                )
            return result

        return self._safe(load, "stock_quotes_range")

    def stock_bars_range(self, start: date, end: date, symbol: str) -> list[StockBar]:
        def load() -> list[StockBar]:
            rows = self._query(
                """
                SELECT stockCode, tradeDate, openPrice, highPrice, lowPrice,
                       closePrice, preClosePrice
                FROM stock_daily_prices
                WHERE tradeDate >= :start AND tradeDate <= :end
                  AND stockCode = :symbol
                ORDER BY tradeDate
                """,
                {
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "symbol": symbol,
                },
            )
            return [
                StockBar(
                    trading_day=_date(row["tradeDate"]),
                    symbol=_text_required(row["stockCode"]),
                    open=_decimal_optional(row["openPrice"]),
                    high=_decimal_optional(row["highPrice"]),
                    low=_decimal_optional(row["lowPrice"]),
                    close=_decimal_optional(row["closePrice"]),
                    previous_close=_decimal_optional(row["preClosePrice"]),
                )
                for row in rows
            ]

        return self._safe(load, "stock_bars_range")

    def daily_bars(self, trading_day: date) -> list[DailyBar]:
        """All SH/SZ daily bars for one trading day, used by limit-count derivation."""

        def load() -> list[DailyBar]:
            rows = self._query(
                """
                SELECT stockCode, closePrice, preClosePrice
                FROM stock_daily_prices
                WHERE tradeDate = :day
                  AND (stockCode LIKE '%.SH' OR stockCode LIKE '%.SZ')
                ORDER BY stockCode
                """,
                {"day": trading_day.isoformat()},
            )
            return [
                DailyBar(
                    symbol=_text_required(row["stockCode"]),
                    close=_decimal_optional(row["closePrice"]),
                    pre_close=_decimal_optional(row["preClosePrice"]),
                )
                for row in rows
            ]

        return self._safe(load, "daily_bars")

    def security_metadata(self) -> SecurityMetadata:
        """Identity, listing dates and observed ST intervals for the SH/SZ universe."""

        def load() -> SecurityMetadata:
            identifiers = self._query(
                """
                SELECT securityId, securityCode, exchange
                FROM research_security_identifier_history
                WHERE identifierType = 'primary' AND exchange IN ('SH', 'SZ')
                """,
                {},
            )
            securities = self._query(
                """
                SELECT securityId, DATE_FORMAT(listedDate, '%Y-%m-%d') AS listedDate
                FROM research_securities
                WHERE exchange IN ('SH', 'SZ')
                """,
                {},
            )
            status_rows = self._query(
                """
                SELECT securityId, statusValue,
                       DATE_FORMAT(effectiveFrom, '%Y-%m-%d') AS effectiveFrom,
                       DATE_FORMAT(effectiveTo, '%Y-%m-%d') AS effectiveTo
                FROM research_security_status_history
                WHERE statusType = 'ST'
                """,
                {},
            )
            listed_by_security = {
                str(row["securityId"]): _date(row["listedDate"])
                for row in securities
                if row.get("listedDate")
            }
            security_by_code: dict[str, str] = {}
            ambiguous: set[str] = set()
            for row in identifiers:
                code = f"{_text_required(row['securityCode'])}.{_text_required(row['exchange'])}"
                security_id = _text_required(row["securityId"])
                existing = security_by_code.get(code)
                if existing is not None and existing != security_id:
                    ambiguous.add(code)
                    continue
                security_by_code[code] = security_id
            for code in ambiguous:
                security_by_code.pop(code, None)
            listed_by_code = {
                code: listed_by_security[security_id]
                for code, security_id in security_by_code.items()
                if security_id in listed_by_security
            }
            intervals: dict[str, list[tuple[date, date | None, str]]] = {}
            for row in status_rows:
                security_id = _text_required(row["securityId"])
                value = _text_required(row["statusValue"])
                if value not in ("ST", "*ST"):
                    continue
                start = _date(row["effectiveFrom"])
                end = _optional_date(row["effectiveTo"])
                intervals.setdefault(security_id, []).append((start, end, value))
            return SecurityMetadata(
                security_by_code=security_by_code,
                listed_by_code=listed_by_code,
                st_intervals={key: tuple(value) for key, value in intervals.items()},
            )

        return self._safe(load, "security_metadata")

    def market_wide_rows(self, start: date, end: date) -> list[MarketWideRow]:
        def load() -> list[MarketWideRow]:
            rows = self._query(
                """
                SELECT dataDate, turnover, marginBalance
                FROM market_data
                WHERE dataDate >= :start AND dataDate <= :end
                ORDER BY dataDate
                """,
                {"start": start.isoformat(), "end": end.isoformat()},
            )
            return [
                MarketWideRow(
                    trading_day=_date(row["dataDate"]),
                    turnover_100m_cny=_decimal_optional(row["turnover"]),
                    margin_balance_100m_cny=_decimal_optional(row["marginBalance"]),
                )
                for row in rows
            ]

        return self._safe(load, "market_wide_rows")

    def index_rows(self, start: date, end: date, symbols: list[str]) -> list[IndexBar]:
        def load() -> list[IndexBar]:
            if not symbols:
                return []
            rows = self._query(
                """
                SELECT indexCode, tradeDate, open, high, low, close, amount, volume
                FROM index_daily
                WHERE tradeDate >= :start AND tradeDate <= :end
                  AND indexCode IN :symbols
                ORDER BY tradeDate, indexCode
                """,
                {
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "symbols": symbols,
                },
                expanding=("symbols",),
            )
            return [
                IndexBar(
                    trading_day=_date(row["tradeDate"]),
                    symbol=_text_required(row["indexCode"]),
                    open=_decimal_optional(row["open"]),
                    high=_decimal_optional(row["high"]),
                    low=_decimal_optional(row["low"]),
                    close=_decimal_optional(row["close"]),
                    amount_source=_decimal_optional(row["amount"]),
                    volume_source=_decimal_optional(row["volume"]),
                )
                for row in rows
            ]

        return self._safe(load, "index_rows")

    def _query(
        self,
        sql: str,
        params: dict,
        *,
        expanding: tuple[str, ...] = (),
    ) -> list[dict]:
        statement = text(sql)
        for name in expanding:
            statement = statement.bindparams(bindparam(name, expanding=True))
        with self._engine.connect() as connection:
            return list(connection.execute(statement, params).mappings())

    def _safe(self, operation: Callable[[], T], operation_name: str) -> T:
        try:
            return operation()
        except ReviewSourceDataError as error:
            log_event(
                "market.review_source_failed",
                level=logging.WARNING,
                source="legacy",
                operation=operation_name,
                reason="bad_data",
                error_type=type(error).__name__,
            )
            raise DomainError("MARKET_REVIEW_SOURCE_BAD_DATA") from None
        except SQLAlchemyError as error:
            if _is_auth_failure(error):
                log_event(
                    "market.review_source_failed",
                    level=logging.ERROR,
                    source="legacy",
                    operation=operation_name,
                    reason="auth_failed",
                    error_type=type(error).__name__,
                )
                raise DomainError("MARKET_REVIEW_SOURCE_AUTH_FAILED") from None
            log_event(
                "market.review_source_failed",
                level=logging.ERROR,
                source="legacy",
                operation=operation_name,
                reason="unavailable",
                error_type=type(error).__name__,
            )
            raise DomainError("MARKET_REVIEW_SOURCE_UNAVAILABLE") from None


def _is_auth_failure(error: SQLAlchemyError) -> bool:
    """Recognize MySQL access-denied errors without inspecting sensitive text."""
    original = getattr(error, "orig", None)
    args = getattr(original, "args", ())
    server_code = args[0] if args and isinstance(args[0], int) else None
    return getattr(original, "sqlstate", None) == "28000" or server_code in {
        1044,
        1045,
        1142,
        1143,
    }


def _date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            pass
    raise ReviewSourceDataError("invalid date")


def _optional_date(value: object) -> date | None:
    return None if value is None else _date(value)


def _row_count(value: object) -> int:
    try:
        count = int(value or 0)
    except (TypeError, ValueError):
        raise ReviewSourceDataError("invalid row count") from None
    if count < 0:
        raise ReviewSourceDataError("negative row count")
    return count


def _time_optional(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, time):
        return value.replace(microsecond=0).isoformat()
    text_value = str(value).strip()
    return text_value or None


def _text_required(value: object) -> str:
    text_value = str(value).strip() if value is not None else ""
    if not text_value:
        raise ReviewSourceDataError("missing text")
    return text_value


def _text_optional(value: object) -> str | None:
    if value is None:
        return None
    return str(value).strip() or None


def _decimal_optional(value: object) -> Decimal | None:
    if value is None:
        return None
    text_value = str(value).strip()
    if not text_value:
        return None
    try:
        number = Decimal(text_value)
    except InvalidOperation:
        raise ReviewSourceDataError("invalid decimal") from None
    if not number.is_finite():
        raise ReviewSourceDataError("non-finite decimal")
    return number
