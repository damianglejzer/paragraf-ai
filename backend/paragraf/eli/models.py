"""Pydantic models for the subset of the ELI API schema we use (see docs/eli_openapi.yaml)."""

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class ActInfo(BaseModel):
    """`ActInfo` schema: basic information about an act."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    eli: str = Field(alias="ELI")
    address: str
    publisher: str
    year: int
    pos: int
    title: str
    type: str
    status: str | None = None
    text_html: bool = Field(default=False, alias="textHTML")
    text_pdf: bool = Field(default=False, alias="textPDF")
    announcement_date: dt.date | None = Field(default=None, alias="announcementDate")
    display_address: str | None = Field(default=None, alias="displayAddress")


class ActList(BaseModel):
    """`acts` schema: a page of search results."""

    model_config = ConfigDict(extra="ignore")

    items: list[ActInfo]
    offset: int = 0
    count: int = 0
    total_count: int = Field(default=0, alias="totalCount")


class ReferenceInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    art: str | None = None
    date: dt.date | None = None


class Act(ActInfo):
    """`Act` schema: full details (only the fields we need)."""

    references: dict[str, list[ReferenceInfo]] = Field(default_factory=dict)
