"""Agent tools: search_law, get_article, follow_reference.

Plain functions over a `LawToolkit`, so the same implementations back the LangGraph agent,
the MCP server and the HTTP API.
"""

import re
from dataclasses import dataclass
from typing import Any

import psycopg
from pydantic import BaseModel

from paragraf.db import repository as repo
from paragraf.parsing.references import to_id_number
from paragraf.retrieval.search import Hit, Mode, Retriever

# How users and statutes name the acts -> act code
ACT_ALIASES: dict[str, str] = {
    "kp": "KP",
    "k.p.": "KP",
    "kodeks pracy": "KP",
    "kodeksu pracy": "KP",
    "kc": "KC",
    "k.c.": "KC",
    "kodeks cywilny": "KC",
    "kodeksu cywilnego": "KC",
    "upk": "UPK",
    "ustawa o prawach konsumenta": "UPK",
    "ustawy o prawach konsumenta": "UPK",
    "prawa konsumenta": "UPK",
}
SUP = "⁰¹²³⁴⁵⁶⁷⁸⁹"
REF_RE = re.compile(
    rf"art\.?\s*(?P<art>\d+[a-z]{{0,3}}(?:[{SUP}]+|\^\d+)?[a-z]{{0,2}})"
    rf"(?:\s*(?:§\s*(?P<par>\d+[a-z]?[{SUP}]*)|ust\.?\s*(?P<ust>\d+[a-z]?[{SUP}]*)))?",
    re.IGNORECASE,
)


class ProvisionView(BaseModel):
    id: str
    citation: str
    full_path: str
    text: str
    hierarchy_titles: list[str] = []
    children: list["ProvisionView"] = []
    references: list[str] = []


def parse_reference(ref: str, default_act: str | None = None) -> str | None:
    """'art. 154 § 1 KP' -> 'KP:art_154:par_1'; also accepts provision ids as-is."""
    ref = ref.strip()
    if re.fullmatch(r"[A-Z]+:art_[\w\-]+(:(par|ust)_\w+)?", ref):
        return ref
    lowered = ref.lower()
    act = next(
        (
            code
            for alias, code in sorted(ACT_ALIASES.items(), key=lambda a: -len(a[0]))
            if alias in lowered
        ),
        default_act,
    )
    match = REF_RE.search(ref)
    if act is None or match is None:
        return None
    art = match["art"].replace("^", "_") if "^" in match["art"] else to_id_number(match["art"])
    pid = f"{act}:art_{art}"
    if match["par"]:
        pid += f":par_{to_id_number(match['par'])}"
    elif match["ust"]:
        pid += f":ust_{to_id_number(match['ust'])}"
    return pid


@dataclass
class LawToolkit:
    conn: psycopg.Connection[Any]
    retriever: Retriever

    def search_law(
        self, query: str, k: int = 8, act: str | None = None, mode: Mode = "full"
    ) -> list[Hit]:
        """Hybrid search over the indexed provisions."""
        return self.retriever.search(query, k=k, mode=mode, act=act)

    def get_article(self, reference: str) -> ProvisionView | None:
        """Full text of a provision by citation ('art. 154 KP') or id, with its sub-units."""
        pid = parse_reference(reference)
        if pid is None:
            return None
        row = repo.get_provision(self.conn, pid)
        if row is None:
            return None
        children = repo.get_children(self.conn, row["id"]) if row["level"] == "article" else []
        return ProvisionView(
            id=row["id"],
            citation=row["citation"],
            full_path=row["full_path"],
            text=row["text"],
            hierarchy_titles=row["hierarchy_titles"],
            children=[_view(c) for c in children],
            references=repo.get_outgoing_references(self.conn, row["id"]),
        )

    def follow_reference(self, provision_id: str, limit: int = 5) -> list[ProvisionView]:
        """Provisions referenced by `provision_id` ("art. 22 § 1", "§ 2"...) within the corpus."""
        out = []
        for target in repo.get_outgoing_references(self.conn, provision_id)[:limit]:
            row = repo.get_provision(self.conn, target)
            if row is not None:
                out.append(_view(row))
        return out


def _view(row: dict[str, Any]) -> ProvisionView:
    return ProvisionView(
        id=row["id"],
        citation=row["citation"],
        full_path=row["full_path"],
        text=row["text"],
        hierarchy_titles=row.get("hierarchy_titles") or [],
    )


def hit_from_view(view: ProvisionView) -> Hit:
    return Hit(
        id=view.id,
        score=0.0,
        text=view.text,
        citation=view.citation,
        full_path=view.full_path,
        ids=[view.id],
        sources={"tool": 1},
    )
