"""Request correlation, elapsed-time logging and the last-resort 500 body.

This middleware is pure ASGI rather than ``BaseHTTPMiddleware`` so the request
context survives into streaming responses and exception paths without a second
task hop. It owns three things that must happen exactly once per request:

1. allocate the request id before any business code runs, and put it on the
   response as ``X-Request-ID``;
2. emit one ``request.completed`` event with method, route template, status and
   duration;
3. turn an unhandled exception into the fixed safe error body while logging only
   the exception *type*, never its message or traceback.
"""

import logging
import time
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .errors import STATUS_CODES, ErrorDetail, ErrorResponse
from .logging import log_event, new_request_id, request_scope

REQUEST_ID_HEADER = "X-Request-ID"


def _mark(request_state: dict[str, Any], code: str) -> None:
    request_state["error_code"] = code


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = new_request_id()
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        started = time.perf_counter()
        observed = {"status": 500, "started": False}

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                observed["started"] = True
                observed["status"] = int(message["status"])
                headers = MutableHeaders(scope=message)
                headers[REQUEST_ID_HEADER] = request_id
            await send(message)

        with request_scope(request_id):
            try:
                await self.app(scope, receive, send_with_id)
            except Exception as exc:  # noqa: BLE001 - boundary of the whole app
                # The exception message and traceback may contain SQL, paths or
                # credentials; only the class name is safe to record.
                log_event(
                    "request.failed",
                    level=logging.ERROR,
                    code="INTERNAL_ERROR",
                    category="internal",
                    status=500,
                    method=scope.get("method", ""),
                    route=_route_template(scope),
                    error_type=type(exc).__name__,
                )
                if observed["started"]:
                    # Headers are already on the wire; a new body would corrupt
                    # the response. The contract is discharged by the log event.
                    raise
                observed["status"] = 500
                _mark(state, "INTERNAL_ERROR")
                response = JSONResponse(
                    status_code=500,
                    content=ErrorResponse(
                        detail=ErrorDetail(
                            code="INTERNAL_ERROR",
                            message="服务内部错误，请稍后重试。",
                            request_id=request_id,
                        )
                    ).model_dump(exclude_none=True),
                    headers={REQUEST_ID_HEADER: request_id},
                )
                await response(scope, receive, send)
            finally:
                duration_ms = round((time.perf_counter() - started) * 1000, 1)
                log_event(
                    "request.completed",
                    method=scope.get("method", ""),
                    route=_route_template(scope),
                    status=observed["status"],
                    duration_ms=duration_ms,
                    error_code=state.get("error_code") or _code_for_status(observed["status"]),
                )


def _route_template(scope: Scope) -> str:
    route = scope.get("route")
    template = getattr(route, "path", None)
    if template:
        return str(template)
    # Unmatched paths are logged as a constant so ids, tokens or legacy urls in
    # the concrete path never reach the log.
    return "unmatched"


def _code_for_status(status: int) -> str | None:
    if status < 400:
        return None
    return STATUS_CODES.get(status)
