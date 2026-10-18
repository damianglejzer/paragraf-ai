"""Evaluation dataset schema and I/O (evals/dataset.jsonl)."""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from paragraf.config import REPO_ROOT

Category = Literal["regular", "multi", "out_of_scope", "tricky"]
DATASET_PATH = REPO_ROOT / "evals" / "dataset.jsonl"


class AutoCheck(BaseModel):
    """Result of the automated quality check of a synthetic item."""

    ids_exist: bool
    supported: bool  # judge: reference answer is supported by the expected provisions
    answerable: bool  # judge: the question can be answered from those provisions
    notes: str = ""


class EvalItem(BaseModel):
    id: str
    question: str
    expected_ids: list[str] = Field(default_factory=list)  # empty for out_of_scope
    reference_answer: str
    category: Category
    verified: bool = False  # True only after human review; synthetic items start False
    source: str = "synthetic:gemini"
    act: str | None = None
    auto_check: AutoCheck | None = None

    @property
    def expects_refusal(self) -> bool:
        return self.category == "out_of_scope"


def load_dataset(path: Path = DATASET_PATH) -> list[EvalItem]:
    with path.open(encoding="utf-8") as f:
        return [EvalItem.model_validate_json(line) for line in f if line.strip()]


def save_dataset(items: list[EvalItem], path: Path = DATASET_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item.model_dump(exclude_none=True), ensure_ascii=False) + "\n")
