"""Identity contracts: request/response shapes for registration and login.

``extra="forbid"`` everywhere, so a client cannot try to set its own role or
owner. Passwords are accepted as plain strings only on input and are never
returned; there is no field capable of echoing a credential back.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=120)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserRead(BaseModel):
    """Safe projection of an account: no credential material is representable."""

    model_config = ConfigDict(extra="forbid")

    id: int
    email: str
    display_name: str
    role: str
    is_active: bool
    created_at: datetime
    last_signed_in_at: datetime | None = None


class SessionRead(BaseModel):
    """The signed-in view of the current session."""

    model_config = ConfigDict(extra="forbid")

    user: UserRead
    expires_at: datetime


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
