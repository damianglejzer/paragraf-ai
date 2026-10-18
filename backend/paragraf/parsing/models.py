"""Validated data model for parsed provisions and cross-references."""

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field, field_validator

ProvisionLevel = Literal["article", "paragraph", "passage"]

PROVISION_ID_PATTERN = r"^[A-Z]+:art_[0-9a-z_\-]+(:(par|ust)_[0-9a-z_]+)?$"


class ActMeta(BaseModel):
    code: str = Field(pattern=r"^[A-Z]+$")
    name: str
    eli: str = Field(pattern=r"^[A-Z]{2,3}/\d{4}/\d+$")  # ELI of the consolidated text
    title: str
    announcement_date: dt.date | None = None


class Provision(BaseModel):
    """One citable unit: an article, or a § / ust. inside an article.

    Points (pkt) and letters (lit.) are folded into the text of their parent unit: they are
    too small to be useful retrieval chunks on their own.
    """

    id: str = Field(pattern=PROVISION_ID_PATTERN)
    act_code: str
    level: ProvisionLevel
    article: str  # display form, e.g. "154", "3¹", "101a"
    unit: str | None = None  # display form, e.g. "§ 1", "ust. 2"
    parent_id: str | None = None  # paragraph/passage -> its article
    hierarchy: list[str] = Field(default_factory=list)  # ["Dział VII", "Rozdział I"]
    hierarchy_titles: list[str] = Field(default_factory=list)
    citation: str  # "art. 154 § 1 KP"
    full_path: str  # "KP, Dział VII, Rozdział I, art. 154 § 1"
    text: str
    repealed: bool = False
    is_chunk: bool  # True for the leaf units that are indexed for retrieval
    order: int = Field(ge=0)

    @field_validator("text")
    @classmethod
    def _text_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("provision text is empty")
        return v


class CrossReference(BaseModel):
    """A reference found in provision text, e.g. "art. 22 § 1" or "art. 5 Kodeksu cywilnego"."""

    source_id: str
    target_act: str
    target_article: str  # id form, e.g. "22", "3_1"
    target_unit: str | None = None  # id form, e.g. "par_1", "ust_2"
    raw: str

    @property
    def target_id(self) -> str:
        base = f"{self.target_act}:art_{self.target_article}"
        return f"{base}:{self.target_unit}" if self.target_unit else base
