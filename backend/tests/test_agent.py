import json
from typing import Any

import pytest

from paragraf.agent.graph import ParagrafAgent
from paragraf.agent.tools import parse_reference
from paragraf.providers.fake import FakeLLM
from paragraf.retrieval.search import Hit


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ("art. 154 § 1 KP", "KP:art_154:par_1"),
        ("Art 118 kc", "KC:art_118"),
        ("art. 27 ust. 1 ustawy o prawach konsumenta", "UPK:art_27:ust_1"),
        ("art. 151¹⁰ Kodeksu pracy", "KP:art_151_10"),
        ("KP:art_3_1", "KP:art_3_1"),
        ("art. 154", None),  # no act given
    ],
)
def test_parse_reference(ref: str, expected: str | None) -> None:
    assert parse_reference(ref) == expected


class StubRetriever:
    last_rewrite = None

    def search(self, query: str, **_: Any) -> list[Hit]:
        return [
            Hit(
                id="KP:art_154:par_1",
                score=1.0,
                text="Wymiar urlopu wynosi 26 dni - jeżeli pracownik jest zatrudniony"
                " co najmniej 10 lat.",
                citation="art. 154 § 1 KP",
                full_path="KP, Dział VII, Rozdział I, art. 154 § 1",
                ids=["KP:art_154:par_1"],
            )
        ]


class StubToolkit:
    conn = None
    retriever = StubRetriever()

    def search_law(self, query: str, **kw: Any) -> list[Hit]:
        return self.retriever.search(query)

    def get_article(self, ref: str) -> None:
        return None

    def follow_reference(self, pid: str, limit: int = 5) -> list[Any]:
        return []


def scripted(plan: dict[str, Any], answer: dict[str, Any]) -> FakeLLM:
    def respond(system: str, prompt: str) -> str:
        return json.dumps(plan if "planistą" in system else answer)

    return FakeLLM(responder=respond)


def agent(llm: FakeLLM, judge: FakeLLM | None = None) -> ParagrafAgent:
    return ParagrafAgent(StubToolkit(), llm, judge)  # type: ignore[arg-type]


def test_refusal_short_circuits_the_graph() -> None:
    llm = scripted({"action": "refuse", "message": "Poza zakresem."}, {})
    state = agent(llm).run("Jak upiec sernik?")
    assert state["answer"].status == "refuse"
    assert [s["node"] for s in state["steps"]] == ["plan"]


def test_clarify_returns_question() -> None:
    llm = scripted({"action": "clarify", "message": "Czego dotyczy problem?"}, {})
    state = agent(llm).run("Mam problem w pracy")
    assert state["answer"].status == "clarify"
    assert state["answer"].answer == "Czego dotyczy problem?"


def test_search_path_answers_and_verifies(monkeypatch: pytest.MonkeyPatch) -> None:
    import paragraf.agent.graph as graph

    monkeypatch.setattr(
        graph,
        "_lookup",
        lambda _tk, pid: {
            "id": pid,
            "citation": "art. 154 § 1 KP",
            "text": StubRetriever().search("")[0].text,
        },
    )
    llm = scripted(
        {"action": "search", "search_query": "wymiar urlopu wypoczynkowego"},
        {
            "status": "answer",
            "answer": "Przysługuje 26 dni urlopu [1].",
            "citations": [
                {
                    "provision_id": "KP:art_154:par_1",
                    "quote": "26 dni - jeżeli pracownik jest zatrudniony co najmniej 10 lat",
                    "claim": "Po 10 latach przysługuje 26 dni urlopu.",
                }
            ],
        },
    )
    judge = FakeLLM(
        responder=lambda _s, _p: json.dumps({"items": [{"index": 1, "verdict": "supports"}]})
    )
    state = agent(llm, judge).run("Ile dni urlopu po 12 latach pracy?")
    assert [s["node"] for s in state["steps"]] == ["plan", "gather", "expand", "answer", "verify"]
    assert state["checks"][0].status == "verified"
    assert state["answer"].answer == "Przysługuje 26 dni urlopu [1]."
