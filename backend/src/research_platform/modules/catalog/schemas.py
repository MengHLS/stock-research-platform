from pydantic import BaseModel, ConfigDict, Field


class EntryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)


class EntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    row_version: int


class EntryList(BaseModel):
    items: list[EntryRead]
    total: int
    offset: int
    limit: int
