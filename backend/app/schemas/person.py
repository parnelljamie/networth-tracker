from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict


class PersonCreate(BaseModel):
    name: str
    color: str | None = None
    date_of_birth: date | None = None
    retirement_age: int = 67
    include_in_household: bool = True


class PersonUpdate(BaseModel):
    name: str | None = None
    color: str | None = None
    date_of_birth: date | None = None
    retirement_age: int | None = None
    include_in_household: bool | None = None
    is_archived: bool | None = None


class PersonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str | None
    date_of_birth: date | None
    retirement_age: int
    include_in_household: bool
    sort_order: int
    is_archived: bool
