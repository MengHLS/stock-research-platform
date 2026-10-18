from dataclasses import dataclass

from research_platform.core.errors import DomainError


@dataclass(frozen=True)
class Actor:
    user_id: int


def require_actor() -> Actor:
    """Replace with verified session resolution when identity is implemented.

    Raises the reviewed ``AUTH_NOT_CONFIGURED`` code instead of a hand-built
    response so the status, HTTP body and log category all come from one table.
    """
    raise DomainError("AUTH_NOT_CONFIGURED")
