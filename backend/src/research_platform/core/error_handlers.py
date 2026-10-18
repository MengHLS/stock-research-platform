"""Map every failure path onto one error body.

The status of a business code comes from the explicit table in ``core.errors``;
nothing here infers it from the code string. Each handler also records the
resolved code and category on the request scope so the request-logging middleware
can emit a single completion event instead of a second failure line.
"""

from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .errors import (
    STATUS_CODES,
    DomainError,
    ErrorDetail,
    ErrorField,
    ErrorResponse,
    spec_for,
)
from .logging import current_request_id


def error_response(
    code: str,
    *,
    message: str | None = None,
    fields: list[ErrorField] | None = None,
) -> JSONResponse:
    spec = spec_for(code)
    body = ErrorResponse(
        detail=ErrorDetail(
            code=spec.code,
            message=message or spec.message,
            request_id=current_request_id(),
            fields=fields or None,
        )
    )
    return JSONResponse(status_code=spec.status, content=body.model_dump(exclude_none=True))


def mark_error(request: Request, code: str) -> None:
    """Attach the resolved code/category for the request completion event."""
    request.scope["state"]["error_code"] = code
    request.scope["state"]["error_category"] = spec_for(code).category.value


def _validation_fields(errors: list[Mapping[str, Any]]) -> list[ErrorField]:
    """Keep the location and the stable type code; drop input, msg and context."""
    fields: list[ErrorField] = []
    for item in errors:
        location = item.get("loc") or ()
        path = ".".join(str(part) for part in location if part != "body") or "body"
        fields.append(ErrorField(path=path, code=str(item.get("type") or "invalid")))
        if len(fields) >= 20:
            break
    return fields


def _http_error_fields(detail: Any) -> list[ErrorField] | None:
    """A raised HTTPException may already carry our own ``{code, message}`` detail."""
    if isinstance(detail, Mapping):
        raw_fields = detail.get("fields")
        if isinstance(raw_fields, list):
            result: list[ErrorField] = []
            for item in raw_fields:
                if isinstance(item, Mapping) and "path" in item and "code" in item:
                    result.append(ErrorField(path=str(item["path"]), code=str(item["code"])))
            return result or None
    return None


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain(request: Request, error: DomainError) -> JSONResponse:
        mark_error(request, error.code)
        return error_response(error.code, message=error.message, fields=error.fields)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, error: RequestValidationError) -> JSONResponse:
        mark_error(request, "VALIDATION_FAILED")
        return error_response("VALIDATION_FAILED", fields=_validation_fields(error.errors()))

    @app.exception_handler(StarletteHTTPException)
    async def handle_http(request: Request, error: StarletteHTTPException) -> JSONResponse:
        detail = error.detail
        explicit = detail.get("code") if isinstance(detail, Mapping) else None
        code = str(explicit) if explicit else STATUS_CODES.get(error.status_code, "REQUEST_INVALID")
        message = detail.get("message") if isinstance(detail, Mapping) else None
        mark_error(request, code)
        return error_response(
            code,
            message=str(message) if message else None,
            fields=_http_error_fields(detail),
        )


def route_template(request: Request) -> str:
    """Route *template*, not the concrete path: paths carry ids and user data."""
    route = request.scope.get("route")
    return getattr(route, "path", "") or "unmatched"
