"""FastAPI backend: streaming chat (SSE), provision preview, eval results, demo protection.

Run locally: uv run uvicorn paragraf.api.main:app --reload --port 8010
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from paragraf import observability
from paragraf.agent.graph import ParagrafAgent
from paragraf.agent.tools import LawToolkit
from paragraf.api import protection
from paragraf.config import REPO_ROOT, get_settings
from paragraf.corpus import TOPICS
from paragraf.db import repository as repo
from paragraf.db.schema import schema_sql
from paragraf.indexing.lemmatize import nlp
from paragraf.providers.base import ProviderUnavailable
from paragraf.providers.factory import make_embedder, make_llm, make_reranker
from paragraf.providers.usage import UsageLog, track
from paragraf.retrieval.search import Retriever

log = logging.getLogger("paragraf.api")
settings = get_settings()

EXAMPLES = [
    {
        "label": "Zwolnienie na L4",
        "question": "Czy mogę zostać zwolniony, kiedy jestem na L4?",
    },
    {
        "label": "Urlop",
        "question": "Ile dni urlopu wypoczynkowego przysługuje mi po 12 latach pracy?",
    },
    {
        "label": "Ciąża",
        "question": "Czy pracodawca może mnie zwolnić, kiedy jestem w ciąży? A co, jeśli mam umowę "
        "na czas określony albo na okres próbny?",
    },
    {
        "label": "Wypowiedzenie",
        "question": "Jak długi jest mój okres wypowiedzenia, jeśli pracuję w firmie od 4 lat?",
    },
    {
        "label": "Zaległy urlop",
        "question": "Co się stanie z moim niewykorzystanym urlopem z zeszłego roku? Czy przepada, "
        "jeśli nie wykorzystam go do końca września?",
    },
]
BUSY_MESSAGE = (
    "Usługa AI jest w tej chwili przeciążona lub niedostępna. "
    "Spróbuj za minutę albo wybierz jedno z przykładowych pytań — te odpowiedzi są zapisane."
)
BUDGET_MESSAGE = (
    "Dzienny budżet zapytań demo został wykorzystany. Do północy (UTC) działają tylko "
    "przykładowe pytania z zapisanymi odpowiedziami."
)


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    history: list[Turn] = Field(default_factory=list, max_length=8)


class Services:
    def __init__(self) -> None:
        self.pool: ConnectionPool[Any] = ConnectionPool(
            settings.database_url,
            min_size=1,
            max_size=4,
            kwargs={"row_factory": dict_row, "autocommit": True},
            open=False,
        )
        self.embedder = make_embedder(settings)
        self.reranker = make_reranker(settings)
        self.llm = make_llm(settings)
        self.judge = make_llm(settings, role="judge")
        self.limiter = protection.RateLimiter(settings.rate_limit_per_minute)


services: Services | None = None


def svc() -> Services:
    assert services is not None, "app not started"
    return services


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    global services
    services = Services()
    services.pool.open()
    with services.pool.connection() as conn:
        conn.execute(schema_sql(settings.embedding_dim).encode())
    nlp()  # load spaCy once at startup instead of on the first request
    log.info("ready (langfuse=%s)", observability.enabled())
    yield
    services.pool.close()


app = FastAPI(title="Paragraf AI", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def format_history(turns: list[Turn]) -> str:
    names = {"user": "Użytkownik", "assistant": "Asystent"}
    return "\n".join(f"{names[t.role]}: {t.content[:1000]}" for t in turns[-6:])


def build_payload(state: dict[str, Any], usage: UsageLog, total_ms: float) -> dict[str, Any]:
    answer = state["answer"]
    checks = state.get("checks", [])
    citations = []
    for i, cit in enumerate(answer.citations, start=1):
        check = next((c for c in checks if c.index == i), None)
        citations.append(
            {
                "index": i,
                "provision_id": check.resolved_id
                if check and check.resolved_id
                else cit.provision_id,
                "citation": check.citation if check else None,
                "quote": cit.quote,
                "claim": cit.claim,
                "status": check.status if check else "uncertain",
                "verdict": check.verdict if check else None,
                "explanation": check.explanation if check else "",
                "quote_score": check.quote_score if check else None,
            }
        )
    plan = state.get("plan")
    return {
        "status": answer.status,
        "answer": answer.answer,
        "citations": citations,
        "steps": state.get("steps", []),
        "rewrite": plan.search_query if plan else None,
        "metrics": {
            "total_ms": round(total_ms),
            "tokens": usage.total_tokens,
            "llm_calls": sum(1 for r in usage.records if not r.cached),
            "cost_usd": round(usage.cost_usd, 6),
            "by_stage": usage.by_stage(),
        },
        "cached": False,
    }


def sse(event: str, data: Any) -> dict[str, str]:
    return {"event": event, "data": json.dumps(data, ensure_ascii=False, default=str)}


async def replay(payload: dict[str, Any]) -> AsyncIterator[dict[str, str]]:
    """Stream a cached answer with the same events as a live one (fast, but not instant)."""
    payload = {**payload, "cached": True}
    for step in payload.get("steps", []):
        yield sse("step", step)
        await asyncio.sleep(0.12)
    async for event in stream_text(payload):
        yield event


async def stream_text(payload: dict[str, Any]) -> AsyncIterator[dict[str, str]]:
    words = payload["answer"].split(" ")
    for i in range(0, len(words), 3):
        yield sse("delta", {"text": " ".join(words[i : i + 3]) + " "})
        await asyncio.sleep(0.02)
    yield sse("final", payload)


def run_agent_sync(
    question: str,
    history: str,
    queue: asyncio.Queue[tuple[str, Any]],
    loop: asyncio.AbstractEventLoop,
) -> None:
    s = svc()

    def emit(kind: str, data: Any) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, (kind, data))

    started = time.perf_counter()
    try:
        with s.pool.connection() as conn, track() as usage:
            retriever = Retriever(conn, s.embedder, s.reranker)
            agent = ParagrafAgent(LawToolkit(conn, retriever), s.llm, s.judge)
            state: dict[str, Any] = {"steps": []}
            for _node, delta in agent.stream(question, history):
                for step in delta.get("steps", []):
                    emit("step", step)
                steps = state["steps"] + list(delta.get("steps", []))
                state.update(delta)
                state["steps"] = steps
            payload = build_payload(state, usage, (time.perf_counter() - started) * 1000)
            protection.record_usage(conn, usage.total_tokens, usage.cost_usd)
            if not history and protection.is_cacheable(payload):
                protection.put_cached(conn, question, payload)
        trace_id = observability.record_trace(question, payload, payload["steps"], usage)
        payload["trace_id"] = trace_id
        emit("result", payload)
    except ProviderUnavailable as exc:
        log.warning("provider unavailable: %s", exc)
        emit("busy", None)
    except Exception as exc:
        log.exception("agent failed")
        emit("error", str(exc))
    finally:
        emit("end", None)


@app.post("/api/chat")
async def chat(req: ChatRequest, request: Request) -> EventSourceResponse:
    question = req.question.strip()

    async def events() -> AsyncIterator[dict[str, str]]:
        s = svc()
        if len(question) > settings.max_query_chars:
            yield sse(
                "error",
                {
                    "code": "too_long",
                    "message": f"Pytanie może mieć maksymalnie {settings.max_query_chars} znaków.",
                },
            )
            return
        with s.pool.connection() as conn:
            cached = None if req.history else protection.get_cached(conn, question)
            exhausted = protection.budget_exhausted(conn, settings.daily_request_budget)
        if cached is not None:
            async for event in replay(cached):
                yield event
            return
        if exhausted:
            yield sse("error", {"code": "budget", "message": BUDGET_MESSAGE})
            return
        if (wait := s.limiter.check(client_ip(request))) > 0:
            yield sse(
                "error",
                {
                    "code": "rate_limited",
                    "message": f"Za dużo pytań naraz. Spróbuj ponownie za {int(wait) + 1} s.",
                },
            )
            return

        queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        task = asyncio.create_task(
            asyncio.to_thread(run_agent_sync, question, format_history(req.history), queue, loop)
        )
        while True:
            kind, data = await queue.get()
            if kind == "step":
                yield sse("step", data)
            elif kind == "result":
                async for event in stream_text(data):
                    yield event
            elif kind == "busy":
                yield sse("error", {"code": "busy", "message": BUSY_MESSAGE})
            elif kind == "error":
                yield sse("error", {"code": "internal", "message": "Coś poszło nie tak."})
            elif kind == "end":
                break
        await task

    return EventSourceResponse(events(), ping=10)


@app.get("/api/provisions/{provision_id}")
def provision(provision_id: str) -> dict[str, Any]:
    s = svc()
    with s.pool.connection() as conn:
        toolkit = LawToolkit(conn, Retriever(conn, s.embedder))
        view = toolkit.get_article(provision_id)
        if view is None:
            raise HTTPException(404, "Provision not found")
        act = conn.execute(
            "SELECT code, name, eli, title, announcement_date FROM acts WHERE code = %s",
            (view.id.split(":")[0],),
        ).fetchone()
        parent = None
        row = repo.get_provision(conn, view.id)
        if row and row["parent_id"]:
            parent = toolkit.get_article(row["parent_id"])
    return {
        "provision": view.model_dump(),
        "article": parent.model_dump() if parent else None,
        "act": {
            **(act or {}),
            "source_url": f"https://api.sejm.gov.pl/eli/acts/{act['eli']}/text.html"
            if act
            else None,
        },
    }


@app.get("/api/examples")
def examples() -> dict[str, Any]:
    return {"examples": EXAMPLES, "topics": TOPICS}


@app.get("/api/eval")
def eval_results() -> dict[str, Any]:
    path = REPO_ROOT / "evals" / "results" / "latest.json"
    if not path.exists():
        raise HTTPException(404, "No eval results yet")
    data: dict[str, Any] = json.loads(path.read_text())
    return data


@app.get("/api/health")
def health() -> dict[str, Any]:
    s = svc()
    with s.pool.connection() as conn:
        n = conn.execute("SELECT count(*) AS n FROM provisions WHERE is_chunk").fetchone()
        today = protection.usage_today(conn)
    return {
        "status": "ok",
        "chunks": n["n"] if n else 0,
        "usage_today": today,
        "daily_budget": settings.daily_request_budget,
        "langfuse": observability.enabled(),
        "models": {
            "llm": settings.llm_model,
            "judge": settings.judge_model,
            "embedding": settings.embedding_model,
            "reranker": settings.reranker_model,
        },
    }
