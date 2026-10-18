"""Ingestion pipeline: discover acts -> download (cached) -> parse -> validate -> store.

Usage: uv run python -m paragraf.ingest
"""

import logging
from collections import Counter

from paragraf.config import get_settings
from paragraf.corpus import in_scope
from paragraf.db import repository as repo
from paragraf.eli.client import EliClient
from paragraf.eli.discovery import TARGET_ACTS, discover
from paragraf.parsing.html_parser import parse_act_html
from paragraf.parsing.models import ActMeta, CrossReference, Provision
from paragraf.parsing.references import extract_references

log = logging.getLogger("paragraf.ingest")


def check_against_struct(provisions: list[Provision], struct: object) -> tuple[int, int]:
    """Compare parsed article ids with the `/struct` tree of the consolidated text section."""

    def walk(node: object, out: set[str], inside: bool) -> None:
        if isinstance(node, list):
            for n in node:
                walk(n, out, inside)
        elif isinstance(node, dict):
            here = inside or "jednolity" in str(node.get("title", "")).lower()
            if here and node.get("type") == "arti":
                out.add(str(node.get("name")))
            walk(node.get("children", []), out, here)

    expected: set[str] = set()
    walk(struct, expected, False)
    parsed = {p.id.split(":art_", 1)[1] for p in provisions if p.level == "article"}
    return len(parsed & expected), len(expected)


def run() -> None:
    settings = get_settings()
    all_provisions: list[Provision] = []
    acts: list[ActMeta] = []
    with EliClient(settings.eli_base_url, cache_dir=settings.raw_dir) as client:
        for target in TARGET_ACTS:
            info = discover(client, target)
            if info is None:
                log.warning("%s: no consolidated text with HTML found, skipping", target.code)
                continue
            act = ActMeta(
                code=target.code,
                name=target.short_name,
                eli=info.eli,
                title=info.title,
                announcement_date=info.announcement_date,
            )
            parsed = parse_act_html(client.get_text_html(info.eli), act)
            try:
                matched, expected = check_against_struct(parsed, client.get_struct(info.eli))
                log.info("%s: struct check %d/%d articles matched", act.code, matched, expected)
            except Exception as exc:  # struct is a sanity check only
                log.warning("%s: struct check skipped (%s)", act.code, exc)
            provisions = [p for p in parsed if in_scope(p.act_code, p.hierarchy)]
            levels = Counter(p.level for p in provisions)
            log.info(
                "%s (%s): %d of %d provisions in demo scope %s, %d chunks",
                act.code,
                act.eli,
                len(provisions),
                len(parsed),
                dict(levels),
                sum(p.is_chunk for p in provisions),
            )
            acts.append(act)
            all_provisions.extend(provisions)

    known_ids = {p.id for p in all_provisions}
    article_ids = {p.id for p in all_provisions if p.level == "article"}
    refs: list[CrossReference] = []
    for p in all_provisions:
        if not p.is_chunk:
            continue
        for ref in extract_references(p):
            if ref.target_id in known_ids:
                refs.append(ref)
            elif f"{ref.target_act}:art_{ref.target_article}" in article_ids:
                refs.append(ref.model_copy(update={"target_unit": None}))
    log.info("cross-references resolved: %d", len(refs))

    with repo.connect() as conn:
        repo.init_schema(conn, settings.embedding_dim)
        conn.execute("DELETE FROM acts WHERE NOT (code = ANY(%s))", ([a.code for a in acts],))
        for act in acts:
            repo.upsert_act(conn, act)
            repo.replace_provisions(
                conn, act.code, [p for p in all_provisions if p.act_code == act.code]
            )
        repo.replace_references(conn, refs)
    log.info("stored %d acts, %d provisions", len(acts), len(all_provisions))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    run()
