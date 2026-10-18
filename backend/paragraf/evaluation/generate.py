"""Generate the synthetic evaluation set (evals/dataset.jsonl) with automated checks.

Usage: uv run python -m paragraf.evaluation.generate [--seed 7]

Every item is synthetic (verified=false). Quality control is automated: expected ids must
exist, and a second, different model judges that the reference answer is supported by the
expected provisions and that the question is answerable from them. Items failing the check
are dropped.
"""

import argparse
import json
import logging
import random
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any

from pydantic import BaseModel, Field

from paragraf.corpus import TOPICS
from paragraf.db import repository as repo
from paragraf.evaluation.dataset import AutoCheck, EvalItem, save_dataset
from paragraf.providers.base import LLM, ProviderUnavailable
from paragraf.providers.factory import make_llm

log = logging.getLogger("paragraf.generate")

# Target counts per act for single-provision questions (sums to ~80 before filtering)
REGULAR_PER_ACT = {"KP": 32, "UPK": 18, "KC": 12}
MULTI_TOTAL = 25
TRICKY_TOTAL = 20
OOS_TOTAL = 20
OVERSAMPLE = 1.3

GEN_SYSTEM = (
    "Tworzysz zbiór ewaluacyjny dla asystenta AI do polskiego prawa. Piszesz po polsku. "
    "Pytania mają brzmieć jak od zwykłego człowieka (nie prawnika): konkretna sytuacja "
    "życiowa, język potoczny, BEZ numerów artykułów i BEZ cytowania słów z przepisu "
    "(parafrazuj). Odpowiedź wzorcowa: 1-3 zdania, wyłącznie na podstawie podanego tekstu."
)


class GenSingle(BaseModel):
    usable: bool = Field(description="false gdy przepis jest zbyt techniczny dla laika")
    question: str
    reference_answer: str


class GenMulti(BaseModel):
    usable: bool = Field(description="false gdy nie da się sensownie połączyć przepisów")
    question: str
    reference_answer: str


class GenOutOfScope(BaseModel):
    questions: list[str]


class Judge(BaseModel):
    answerable: bool = Field(description="czy na pytanie da się odpowiedzieć z tych przepisów")
    supported: bool = Field(description="czy odpowiedź wzorcowa wynika z tych przepisów")
    notes: str = ""


def _ask(llm: LLM, system: str, prompt: str, schema: type[BaseModel]) -> Any:
    resp = llm.complete(system, prompt, json_schema=schema, temperature=0.7)
    return schema.model_validate_json(resp.text)


def _fmt(row: dict[str, Any]) -> str:
    return f"[{row['citation']}] ({' > '.join(row['hierarchy_titles'])})\n{row['text']}"


def gen_regular(llm: LLM, row: dict[str, Any]) -> EvalItem | None:
    out: GenSingle = _ask(
        llm,
        GEN_SYSTEM,
        f"Przepis:\n{_fmt(row)}\n\nNapisz jedno pytanie, na które ten przepis odpowiada.",
        GenSingle,
    )
    if not out.usable:
        return None
    return EvalItem(
        id="",
        question=out.question,
        expected_ids=[row["id"]],
        reference_answer=out.reference_answer,
        category="regular",
        act=row["act_code"],
    )


def gen_multi(llm: LLM, a: dict[str, Any], b: dict[str, Any]) -> EvalItem | None:
    out: GenMulti = _ask(
        llm,
        GEN_SYSTEM,
        f"Przepis A:\n{_fmt(a)}\n\nPrzepis B:\n{_fmt(b)}\n\n"
        "Napisz jedno pytanie, którego pełna odpowiedź WYMAGA obu przepisów.",
        GenMulti,
    )
    if not out.usable:
        return None
    return EvalItem(
        id="",
        question=out.question,
        expected_ids=[a["id"], b["id"]],
        reference_answer=out.reference_answer,
        category="multi",
        act=a["act_code"],
    )


def gen_tricky(llm: LLM, row: dict[str, Any]) -> EvalItem | None:
    out: GenSingle = _ask(
        llm,
        GEN_SYSTEM,
        f"Przepis:\n{_fmt(row)}\n\nNapisz podchwytliwe pytanie z FAŁSZYWYM założeniem "
        "sprzecznym z tym przepisem (np. błędna liczba dni, kwota, termin albo odwrócona "
        "reguła), zadane tak, jakby pytający był pewny swojej wersji. Odpowiedź wzorcowa "
        "ma prostować błędne założenie na podstawie przepisu.",
        GenSingle,
    )
    if not out.usable:
        return None
    return EvalItem(
        id="",
        question=out.question,
        expected_ids=[row["id"]],
        reference_answer=out.reference_answer,
        category="tricky",
        act=row["act_code"],
    )


def gen_out_of_scope(llm: LLM, acts: list[str], n: int) -> list[EvalItem]:
    out: GenOutOfScope = _ask(
        llm,
        GEN_SYSTEM,
        f"Asystent zna WYŁĄCZNIE wybrane fragmenty aktów {', '.join(acts)} na tematy: "
        f"{'; '.join(TOPICS)}. Napisz {n} różnorodnych pytań, "
        "na które NIE da się odpowiedzieć na podstawie tych aktów: około połowa z innych "
        "dziedzin prawa (np. prawo karne, ruch drogowy, budowlane, VAT, spadki według "
        "postępowania sądowego, rozwód, alimenty, prawo UE) i około połowa zupełnie "
        "nieprawnicza (gotowanie, programowanie, sport). Unikaj tematów z listy powyżej.",
        GenOutOfScope,
    )
    return [
        EvalItem(
            id="",
            question=q,
            reference_answer="Odmowa: pytanie wykracza poza zakres dostępnych przepisów.",
            category="out_of_scope",
        )
        for q in out.questions[:n]
    ]


def auto_check(judge: LLM, item: EvalItem, rows: dict[str, dict[str, Any]]) -> AutoCheck:
    if item.category == "out_of_scope":
        return AutoCheck(ids_exist=True, supported=True, answerable=False)
    if not all(i in rows for i in item.expected_ids):
        return AutoCheck(ids_exist=False, supported=False, answerable=False)
    provisions = "\n\n".join(_fmt(rows[i]) for i in item.expected_ids)
    out: Judge = _ask(
        judge,
        "Jesteś surowym recenzentem zbioru testowego dla asystenta prawnego.",
        f"Przepisy:\n{provisions}\n\nPytanie: {item.question}\n"
        f"Odpowiedź wzorcowa: {item.reference_answer}\n\n"
        "Oceń, czy na pytanie da się odpowiedzieć na podstawie tych przepisów i czy "
        "odpowiedź wzorcowa jest z nimi zgodna.",
        Judge,
    )
    return AutoCheck(
        ids_exist=True, supported=out.supported, answerable=out.answerable, notes=out.notes
    )


def _parallel(fns: list[Callable[[], Any]], workers: int = 4) -> list[Any]:
    def safe(fn: Callable[[], Any]) -> Any:
        try:
            return fn()
        except (ProviderUnavailable, ValueError) as exc:
            log.warning("generation failed: %s", exc)
            return None

    with ThreadPoolExecutor(workers) as pool:
        return list(pool.map(safe, fns))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    rng = random.Random(args.seed)
    gen, judge = make_llm(role="answer"), make_llm(role="judge")

    with repo.connect() as conn:
        rows = conn.execute(
            "SELECT id, act_code, citation, hierarchy_titles, text FROM provisions "
            "WHERE is_chunk AND NOT repealed AND length(text) BETWEEN 120 AND 1500"
        ).fetchall()
        refs = conn.execute(
            "SELECT r.source_id, r.target_id FROM provision_refs r "
            "JOIN provisions p ON p.id = r.target_id "
            "WHERE p.is_chunk AND NOT p.repealed AND split_part(r.source_id, ':', 2) "
            "<> split_part(r.target_id, ':', 2)"
        ).fetchall()
        acts = [r["name"] for r in conn.execute("SELECT name FROM acts ORDER BY code")]
    by_id = {r["id"]: r for r in rows}
    by_act: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_act.setdefault(r["act_code"], []).append(r)

    jobs: list[Callable[[], Any]] = []
    used: set[str] = set()
    for act, n in REGULAR_PER_ACT.items():
        for row in rng.sample(by_act[act], int(n * OVERSAMPLE)):
            used.add(row["id"])
            jobs.append(partial(gen_regular, gen, row))
    pairs = [
        (by_id[r["source_id"]], by_id[r["target_id"]])
        for r in refs
        if r["source_id"] in by_id and r["target_id"] in by_id
    ]
    for a, b in rng.sample(pairs, int(MULTI_TOTAL * OVERSAMPLE)):
        jobs.append(partial(gen_multi, gen, a, b))
    tricky_pool = [r for r in rows if r["id"] not in used and any(ch.isdigit() for ch in r["text"])]
    for row in rng.sample(tricky_pool, int(TRICKY_TOTAL * OVERSAMPLE)):
        jobs.append(partial(gen_tricky, gen, row))
    log.info("generating %d candidates", len(jobs))
    candidates = [c for c in _parallel(jobs) if c is not None]
    oos = gen_out_of_scope(gen, acts, OOS_TOTAL)

    checks = _parallel([partial(auto_check, judge, c, by_id) for c in candidates])
    kept: list[EvalItem] = []
    for item, check in zip(candidates, checks, strict=True):
        if check and check.ids_exist and check.supported and check.answerable:
            kept.append(item.model_copy(update={"auto_check": check}))
    limits = {
        "regular": sum(REGULAR_PER_ACT.values()),
        "multi": MULTI_TOTAL,
        "tricky": TRICKY_TOTAL,
    }
    final: list[EvalItem] = []
    for cat, limit in limits.items():
        final += [i for i in kept if i.category == cat][:limit]
    final += [o.model_copy(update={"auto_check": auto_check(judge, o, by_id)}) for o in oos]
    final = [i.model_copy(update={"id": f"q{n:03d}"}) for n, i in enumerate(final, start=1)]
    save_dataset(final)
    stats = {cat: sum(i.category == cat for i in final) for cat in [*limits, "out_of_scope"]}
    log.info(
        "candidates=%d passed_check=%d saved=%d %s",
        len(candidates),
        len(kept),
        len(final),
        json.dumps(stats),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    main()
