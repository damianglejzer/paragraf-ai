"""Find, for each target statute, the newest consolidated text (tekst jednolity) with HTML.

A consolidated text is published as a separate act of type "Obwieszczenie" whose title ends
with "...w sprawie ogłoszenia jednolitego tekstu ustawy <name>". See docs/DECISIONS.md (D1).
"""

import re
from dataclasses import dataclass

from paragraf.eli.client import EliClient
from paragraf.eli.models import ActInfo


@dataclass(frozen=True)
class TargetAct:
    code: str  # short code used in chunk ids and citations, e.g. "KP"
    name: str  # statute name as it appears in the consolidated text title
    short_name: str  # display name, e.g. "Kodeks pracy"


ALL_ACTS: list[TargetAct] = [
    TargetAct("KP", "Kodeks pracy", "Kodeks pracy"),
    TargetAct("KC", "Kodeks cywilny", "Kodeks cywilny"),
    TargetAct("UPK", "o prawach konsumenta", "Ustawa o prawach konsumenta"),
    TargetAct("OP", "Ordynacja podatkowa", "Ordynacja podatkowa"),
    TargetAct("ODO", "o ochronie danych osobowych", "Ustawa o ochronie danych osobowych"),
    TargetAct("KRO", "Kodeks rodzinny i opiekuńczy", "Kodeks rodzinny i opiekuńczy"),
    TargetAct("KW", "Kodeks wykroczeń", "Kodeks wykroczeń"),
]
# Acts parsed by the pipeline; the indexed demo corpus is narrowed further in corpus.py
TARGET_ACTS: list[TargetAct] = [a for a in ALL_ACTS if a.code in ("KP", "KC", "UPK")]

_TITLE_PREFIX = "jednolitego tekstu ustawy"


def _normalize(text: str) -> str:
    text = text.replace("\xa0", " ").replace("–", "-")
    return re.sub(r"\s+", " ", text).strip().rstrip(".").lower()


def is_consolidated_text_of(act: ActInfo, name: str) -> bool:
    """True when `act` is the consolidated text of exactly the statute `name`."""
    title = _normalize(act.title)
    wanted = _normalize(name)
    return act.type == "Obwieszczenie" and (
        title.endswith(f"{_TITLE_PREFIX} - {wanted}") or title.endswith(f"{_TITLE_PREFIX} {wanted}")
    )


def pick_newest_html(candidates: list[ActInfo], name: str) -> ActInfo | None:
    matching = [a for a in candidates if is_consolidated_text_of(a, name) and a.text_html]
    if not matching:
        return None
    return max(matching, key=lambda a: (a.announcement_date or a.year, a.pos))


def discover(client: EliClient, target: TargetAct) -> ActInfo | None:
    result = client.search(
        title=f"{_TITLE_PREFIX} {target.name}",
        type="Obwieszczenie",
        publisher="DU",
        limit=200,
    )
    return pick_newest_html(result.items, target.name)
