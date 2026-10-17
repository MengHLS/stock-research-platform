from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class JobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_type: Literal["system.check"]
    idempotency_key: str = Field(min_length=8, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_type: str
    state: Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED"]
    attempts: int
    result: dict | None
    error_code: str | None
