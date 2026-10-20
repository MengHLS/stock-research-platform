"""Error taxonomy and the single public error body.

Rules (see docs/architecture.md "统一错误与日志"):

- the HTTP status of a business code comes from the explicit table below, never
  from a suffix or prefix convention on the code string;
- every failure is ``{"detail": {code, message, request_id, fields?}}`` and stays
  on its real HTTP status (no error wrapped in a 200 response);
- ``fields`` only carries a stable path and a stable code, never raw input;
- unexpected failures use one fixed safe message, and the details go to the
  redacted log instead of the response.
"""

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ErrorCategory(StrEnum):
    """Coarse failure family used for logging and client-side handling."""

    REQUEST = "request"
    VALIDATION = "validation"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    RATE_LIMITED = "rate_limited"
    INTERNAL = "internal"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ErrorSpec:
    """Controlled definition of one error code."""

    code: str
    status: int
    category: ErrorCategory
    message: str


# Explicit mapping. Add a row here before raising a new DomainError code so the
# status and the safe message are reviewed together with the code.
ERROR_SPECS: dict[str, ErrorSpec] = {
    "REQUEST_INVALID": ErrorSpec(
        "REQUEST_INVALID", 400, ErrorCategory.REQUEST, "请求内容无法处理。"
    ),
    "AUTHENTICATION_REQUIRED": ErrorSpec(
        "AUTHENTICATION_REQUIRED", 401, ErrorCategory.AUTHENTICATION, "需要登录后访问。"
    ),
    "INVALID_CREDENTIALS": ErrorSpec(
        "INVALID_CREDENTIALS", 401, ErrorCategory.AUTHENTICATION, "邮箱或密码不正确。"
    ),
    "ACCOUNT_LOCKED": ErrorSpec(
        "ACCOUNT_LOCKED", 429, ErrorCategory.RATE_LIMITED, "失败次数过多，账号已临时锁定。"
    ),
    "EMAIL_ALREADY_REGISTERED": ErrorSpec(
        "EMAIL_ALREADY_REGISTERED", 409, ErrorCategory.CONFLICT, "该邮箱已注册。"
    ),
    "REGISTRATION_CLOSED": ErrorSpec(
        "REGISTRATION_CLOSED", 403, ErrorCategory.AUTHORIZATION, "当前不允许自助注册。"
    ),
    "INVITATION_CODE_REQUIRED": ErrorSpec(
        "INVITATION_CODE_REQUIRED", 403, ErrorCategory.AUTHORIZATION, "注册需要邀请码。"
    ),
    "INVITATION_CODE_INVALID": ErrorSpec(
        "INVITATION_CODE_INVALID", 403, ErrorCategory.AUTHORIZATION, "邀请码无效。"
    ),
    "INVITATION_CODE_EXPIRED": ErrorSpec(
        "INVITATION_CODE_EXPIRED", 403, ErrorCategory.AUTHORIZATION, "邀请码已过期。"
    ),
    "INVITATION_CODE_ALREADY_USED": ErrorSpec(
        "INVITATION_CODE_ALREADY_USED", 403, ErrorCategory.AUTHORIZATION, "邀请码已被使用。"
    ),
    "PASSWORD_TOO_WEAK": ErrorSpec(
        "PASSWORD_TOO_WEAK", 422, ErrorCategory.VALIDATION, "密码强度不足。"
    ),
    "PERMISSION_DENIED": ErrorSpec(
        "PERMISSION_DENIED", 403, ErrorCategory.AUTHORIZATION, "无权访问该资源。"
    ),
    "ENTRY_NOT_FOUND": ErrorSpec(
        "ENTRY_NOT_FOUND", 404, ErrorCategory.NOT_FOUND, "未找到该模式目录记录。"
    ),
    "JOB_NOT_FOUND": ErrorSpec("JOB_NOT_FOUND", 404, ErrorCategory.NOT_FOUND, "未找到该作业。"),
    "ROUTE_NOT_FOUND": ErrorSpec("ROUTE_NOT_FOUND", 404, ErrorCategory.NOT_FOUND, "接口不存在。"),
    "IDEMPOTENCY_CONFLICT": ErrorSpec(
        "IDEMPOTENCY_CONFLICT", 409, ErrorCategory.CONFLICT, "同一幂等键已用于不同请求。"
    ),
    "METHOD_NOT_ALLOWED": ErrorSpec(
        "METHOD_NOT_ALLOWED", 405, ErrorCategory.REQUEST, "该接口不支持此 HTTP 方法。"
    ),
    "VALIDATION_FAILED": ErrorSpec(
        "VALIDATION_FAILED", 422, ErrorCategory.VALIDATION, "请求参数校验未通过。"
    ),
    "RATE_LIMITED": ErrorSpec(
        "RATE_LIMITED", 429, ErrorCategory.RATE_LIMITED, "请求过于频繁，请稍后重试。"
    ),
    "INTERNAL_ERROR": ErrorSpec(
        "INTERNAL_ERROR", 500, ErrorCategory.INTERNAL, "服务内部错误，请稍后重试。"
    ),
    "SERVICE_UNAVAILABLE": ErrorSpec(
        "SERVICE_UNAVAILABLE", 503, ErrorCategory.UNAVAILABLE, "服务暂不可用。"
    ),
    "AUTH_NOT_CONFIGURED": ErrorSpec(
        "AUTH_NOT_CONFIGURED",
        503,
        ErrorCategory.UNAVAILABLE,
        "登录模块尚未接入；私人资源不可访问。",
    ),
    "SOURCE_NOT_CONFIGURED": ErrorSpec(
        "SOURCE_NOT_CONFIGURED", 503, ErrorCategory.UNAVAILABLE, "研究数据源尚未配置。"
    ),
    "MARKET_SYMBOL_INVALID": ErrorSpec(
        "MARKET_SYMBOL_INVALID", 400, ErrorCategory.REQUEST, "股票代码或周期无法识别。"
    ),
    "MARKET_DATA_UNAVAILABLE": ErrorSpec(
        "MARKET_DATA_UNAVAILABLE", 404, ErrorCategory.NOT_FOUND, "该标的没有可用行情数据。"
    ),
    "MARKET_SOURCE_DISABLED": ErrorSpec(
        "MARKET_SOURCE_DISABLED", 503, ErrorCategory.UNAVAILABLE, "外部行情访问已关闭。"
    ),
    "MARKET_SOURCE_UNAVAILABLE": ErrorSpec(
        "MARKET_SOURCE_UNAVAILABLE", 503, ErrorCategory.UNAVAILABLE, "外部行情服务暂不可用。"
    ),
    "MARKET_SOURCE_BAD_RESPONSE": ErrorSpec(
        "MARKET_SOURCE_BAD_RESPONSE",
        502,
        ErrorCategory.UNAVAILABLE,
        "外部行情返回内容无法解析。",
    ),
    "MARKET_SOURCE_NOT_CONFIGURED": ErrorSpec(
        "MARKET_SOURCE_NOT_CONFIGURED", 503, ErrorCategory.UNAVAILABLE, "该行情源未配置。"
    ),
    "MARKET_SOURCE_PERMISSION_DENIED": ErrorSpec(
        "MARKET_SOURCE_PERMISSION_DENIED",
        503,
        ErrorCategory.UNAVAILABLE,
        "当前行情账号无该接口权限。",
    ),
    "MARKET_SOURCE_RATE_LIMITED": ErrorSpec(
        "MARKET_SOURCE_RATE_LIMITED", 429, ErrorCategory.RATE_LIMITED, "行情源调用频率受限。"
    ),
    "MARKET_REVIEW_RANGE_INVALID": ErrorSpec(
        "MARKET_REVIEW_RANGE_INVALID", 400, ErrorCategory.REQUEST, "复盘查询区间或窗口不合法。"
    ),
    "MARKET_REVIEW_DATE_UNAVAILABLE": ErrorSpec(
        "MARKET_REVIEW_DATE_UNAVAILABLE", 404, ErrorCategory.NOT_FOUND, "该日期没有可用的复盘数据。"
    ),
    "MARKET_REVIEW_SOURCE_UNAVAILABLE": ErrorSpec(
        "MARKET_REVIEW_SOURCE_UNAVAILABLE",
        503,
        ErrorCategory.UNAVAILABLE,
        "历史复盘数据源暂不可用。",
    ),
    "MARKET_REVIEW_SOURCE_AUTH_FAILED": ErrorSpec(
        "MARKET_REVIEW_SOURCE_AUTH_FAILED",
        503,
        ErrorCategory.UNAVAILABLE,
        "历史复盘数据源认证或授权失败，请检查源库账号、密码和访问白名单。",
    ),
    "MARKET_REVIEW_SOURCE_BAD_DATA": ErrorSpec(
        "MARKET_REVIEW_SOURCE_BAD_DATA",
        502,
        ErrorCategory.UNAVAILABLE,
        "历史复盘数据源包含无法识别的数据。",
    ),
    "MARKET_STATE_DATE_UNAVAILABLE": ErrorSpec(
        "MARKET_STATE_DATE_UNAVAILABLE",
        404,
        ErrorCategory.NOT_FOUND,
        "该日期没有可用的市场状态。",
    ),
    "MARKET_STATE_SOURCE_UNAVAILABLE": ErrorSpec(
        "MARKET_STATE_SOURCE_UNAVAILABLE",
        503,
        ErrorCategory.UNAVAILABLE,
        "市场状态数据源暂不可用。",
    ),
    "MARKET_STATE_SOURCE_BAD_DATA": ErrorSpec(
        "MARKET_STATE_SOURCE_BAD_DATA",
        502,
        ErrorCategory.UNAVAILABLE,
        "市场状态数据源未通过完整性校验。",
    ),
    "DATABASE_UNAVAILABLE": ErrorSpec(
        "DATABASE_UNAVAILABLE", 503, ErrorCategory.UNAVAILABLE, "数据库暂不可用。"
    ),
}

# Unknown business codes stay a client-side request failure instead of a 500:
# raising an unmapped code is still a review gap, not evidence of a server crash.
FALLBACK_SPEC = ErrorSpec("REQUEST_INVALID", 400, ErrorCategory.REQUEST, "请求无法处理。")

# Status used when a framework exception only carries an HTTP status.
STATUS_CODES: dict[int, str] = {
    400: "REQUEST_INVALID",
    401: "AUTHENTICATION_REQUIRED",
    403: "PERMISSION_DENIED",
    404: "ROUTE_NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "IDEMPOTENCY_CONFLICT",
    422: "VALIDATION_FAILED",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


def spec_for(code: str) -> ErrorSpec:
    return ERROR_SPECS.get(code, FALLBACK_SPEC)


def http_status_for(code: str) -> int:
    return spec_for(code).status


class ErrorField(BaseModel):
    """Field-level failure marker: stable path and stable code only."""

    model_config = ConfigDict(extra="forbid")

    path: str
    code: str


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    request_id: str | None = None
    fields: list[ErrorField] | None = None


class ErrorResponse(BaseModel):
    """Public error body shared by every route."""

    model_config = ConfigDict(extra="forbid")

    detail: ErrorDetail


# Default OpenAPI error surface so the generated TypeScript client can type
# failures without hand-maintained copies.
DEFAULT_ERROR_RESPONSES: dict[int | str, dict] = {
    400: {"model": ErrorResponse, "description": "Request cannot be processed"},
    401: {"model": ErrorResponse, "description": "Authentication required"},
    403: {"model": ErrorResponse, "description": "Permission denied"},
    404: {"model": ErrorResponse, "description": "Resource or route not found"},
    405: {"model": ErrorResponse, "description": "HTTP method not supported"},
    409: {"model": ErrorResponse, "description": "Conflict with existing state"},
    422: {"model": ErrorResponse, "description": "Request validation failed"},
    429: {"model": ErrorResponse, "description": "Rate limited"},
    500: {"model": ErrorResponse, "description": "Unexpected server failure"},
    503: {"model": ErrorResponse, "description": "Service or dependency unavailable"},
}


class DomainError(Exception):
    """Business failure carrying a reviewed error code."""

    def __init__(
        self,
        code: str,
        message: str = "",
        *,
        fields: list[ErrorField] | None = None,
    ) -> None:
        self.spec = spec_for(code)
        self.code = code
        self.message = message or self.spec.message
        self.fields = list(fields or ())
        super().__init__(self.message)
