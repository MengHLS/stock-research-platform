from dataclasses import dataclass

from fastapi import HTTPException


@dataclass(frozen=True)
class Actor:
    user_id: int


def require_actor() -> Actor:
    """Replace with verified session resolution when identity is implemented."""
    raise HTTPException(
        status_code=503,
        detail={
            "code": "AUTH_NOT_CONFIGURED",
            "message": "登录模块尚未接入；私人资源不可访问。",
        },
    )
