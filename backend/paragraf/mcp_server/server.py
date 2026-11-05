"""MCP server exposing Polish-law search and provision lookup (official MCP Python SDK v2).

Run over stdio (e.g. for Claude Desktop / Claude Code):
    uv run python -m paragraf.mcp_server.server
or over streamable HTTP:
    uv run python -m paragraf.mcp_server.server --http --port 8765
"""

import argparse
from functools import lru_cache
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from paragraf.agent.tools import LawToolkit
from paragraf.corpus import CORPUS_SCOPE, TOPICS
from paragraf.db import repository as repo
from paragraf.providers.factory import make_embedder, make_llm, make_reranker
from paragraf.retrieval.rewrite import QueryRewriter
from paragraf.retrieval.search import Retriever

mcp = MCPServer(
    name="paragraf",
    title="Asystent Prawa Pracy — Polish labour law",
    instructions=(
        "Search and read provisions of selected Polish statutes (Kodeks pracy, Kodeks cywilny, "
        "ustawa o prawach konsumenta). Always cite provisions by their `citation` field. "
        "Texts come from consolidated texts published via the Sejm ELI API. Not legal advice."
    ),
    version="0.1.0",
)
READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)


@lru_cache(maxsize=1)
def toolkit() -> LawToolkit:
    import psycopg
    from psycopg.rows import dict_row

    from paragraf.config import get_settings

    conn = psycopg.connect(get_settings().database_url, row_factory=dict_row, autocommit=True)
    retriever = Retriever(
        conn, make_embedder(), make_reranker(), rewriter=QueryRewriter(make_llm())
    )
    return LawToolkit(conn, retriever)


@mcp.tool(annotations=READ_ONLY)
def search_law(query: str, k: int = 8, act: str | None = None) -> list[dict[str, Any]]:
    """Hybrid search (lemmatized full-text + vectors + reranker) over indexed provisions.

    Args:
        query: question or keywords in Polish, e.g. "ile dni urlopu po 10 latach pracy"
        k: number of results (1-20)
        act: optional act code filter: KP, KC or UPK
    """
    hits = toolkit().search_law(query, k=max(1, min(k, 20)), act=act)
    return [
        {"id": h.id, "citation": h.citation, "path": h.full_path, "text": h.text, "score": h.score}
        for h in hits
    ]


@mcp.tool(annotations=READ_ONLY)
def get_article(reference: str) -> dict[str, Any]:
    """Full text of a provision by citation or id, with its paragraphs and outgoing references.

    Args:
        reference: e.g. "art. 154 KP", "art. 27 ust. 1 ustawy o prawach konsumenta",
            "KC:art_118"
    """
    view = toolkit().get_article(reference)
    if view is None:
        return {"error": f"Provision not found in the corpus: {reference}"}
    return view.model_dump()


@mcp.tool(annotations=READ_ONLY)
def follow_reference(provision_id: str) -> list[dict[str, Any]]:
    """Provisions that the given provision refers to (e.g. "art. 22 § 1", "§ 2").

    Args:
        provision_id: id returned by search_law/get_article, e.g. "KP:art_154:par_3"
    """
    return [v.model_dump() for v in toolkit().follow_reference(provision_id)]


@mcp.resource("paragraf://corpus")
def corpus() -> dict[str, Any]:
    """Which statutes and topics are indexed."""
    with repo.connect() as conn:
        acts = conn.execute("SELECT code, name, eli, announcement_date FROM acts").fetchall()
    return {
        "acts": [{**a, "announcement_date": str(a["announcement_date"])} for a in acts],
        "scope": {
            code: [" / ".join(p) for p in prefixes] for code, prefixes in CORPUS_SCOPE.items()
        },
        "topics": TOPICS,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--http", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.http:
        mcp.run("streamable-http", port=args.port)
    else:
        mcp.run("stdio")


if __name__ == "__main__":
    main()
