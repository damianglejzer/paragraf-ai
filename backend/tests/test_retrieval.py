import json
from pathlib import Path

from paragraf.indexing.index import NAIVE_CHUNK_CHARS, embedding_text, naive_chunks
from paragraf.providers.cache import DiskCache
from paragraf.providers.fake import FakeEmbedder, FakeLLM
from paragraf.providers.rerankers import LLMReranker
from paragraf.retrieval.search import Hit, build_tsquery, rerank_hits, rrf_fuse


def hit(pid: str, source: str = "x", rank: int = 1) -> Hit:
    return Hit(id=pid, score=0.0, text=pid, citation=pid, ids=[pid], sources={source: rank})


def test_rrf_rewards_agreement_between_retrievers() -> None:
    vector = [hit("A", "vector", 1), hit("B", "vector", 2), hit("C", "vector", 3)]
    fulltext = [hit("C", "fulltext", 1), hit("B", "fulltext", 2), hit("D", "fulltext", 3)]
    fused = rrf_fuse(vector, fulltext)
    # being in both lists beats rank 1 in a single list
    assert {h.id for h in fused[:2]} == {"B", "C"}
    assert fused[0].sources == {"vector": 3, "fulltext": 1}
    assert {h.id for h in fused} == {"A", "B", "C", "D"}


def test_rrf_scores_follow_formula() -> None:
    fused = rrf_fuse([hit("A")], [hit("A")], k=60)
    assert abs(fused[0].score - 2 / 61) < 1e-12


def test_build_tsquery_uses_lemmas_with_or() -> None:
    q = build_tsquery("Ile dni urlopu przysługuje pracownikowi?")
    assert q is not None
    assert "'urlop'" in q and "'pracownik'" in q and " | " in q


def test_build_tsquery_empty_for_stopwords_only() -> None:
    assert build_tsquery("czy to jest?") is None


def test_embedding_text_has_contextual_header() -> None:
    row = {
        "citation": "art. 154 § 2 KP",
        "hierarchy_titles": ["Urlopy pracownicze", "Urlopy wypoczynkowe"],
        "text": "Wymiar urlopu ustala się proporcjonalnie.",
    }
    text = embedding_text(row, "Kodeks pracy")
    assert text.splitlines()[0] == "Kodeks pracy — Urlopy pracownicze > Urlopy wypoczynkowe"
    assert "art. 154 § 2 KP" in text


def test_naive_chunks_cover_text_and_track_provisions() -> None:
    rows = [{"id": f"KP:art_{i}", "text": "x" * 450} for i in range(1, 6)]
    chunks = naive_chunks(rows)
    assert all(len(c) <= NAIVE_CHUNK_CHARS for c, _ in chunks)
    assert chunks[0][1] == ["KP:art_1", "KP:art_2", "KP:art_3"]
    covered = {pid for _, ids in chunks for pid in ids}
    assert covered == {r["id"] for r in rows}


def test_fake_embedder_is_deterministic_and_lexical() -> None:
    emb = FakeEmbedder(64)
    a, b, c = emb.embed(["urlop wypoczynkowy", "urlopu wypoczynkowego", "podatek"], "document")
    assert emb.embed(["urlop wypoczynkowy"], "query")[0] == a
    sim = lambda x, y: sum(i * j for i, j in zip(x, y, strict=True))  # noqa: E731
    assert sim(a, b) > sim(a, c)


def test_llm_reranker_reorders_and_keeps_omitted_candidates() -> None:
    llm = FakeLLM(responder=lambda _s, _p: json.dumps({"ranking": [2, 0]}))
    hits = [hit("A"), hit("B"), hit("C")]
    out = rerank_hits("pytanie", hits, LLMReranker(llm), top_n=3)
    assert [h.id for h in out] == ["C", "A", "B"]
    assert out[0].sources["rerank"] == 1


def test_disk_cache_roundtrip(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path / "c.sqlite")
    key = DiskCache.key("emb", "model", "tekst")
    assert cache.get(key) is None
    cache.set(key, [0.1, 0.2])
    assert cache.get_many([key, "missing"]) == {key: [0.1, 0.2]}


def test_rate_limiter_allows_burst_then_throttles(monkeypatch: object) -> None:
    import paragraf.providers.gemini as g

    sleeps: list[float] = []
    monkeypatch.setattr(g.time, "sleep", lambda s: sleeps.append(s))  # type: ignore[attr-defined]
    g._RateLimiter._calls.pop("test-model", None)
    for _ in range(3):
        g._RateLimiter.wait("test-model", rpm=3)
    assert sleeps == []  # burst within the limit
    g._RateLimiter.wait("test-model", rpm=3)
    assert len(sleeps) == 1 and 59 < sleeps[0] <= 60


def test_extract_json_strips_fences_and_trailing_text() -> None:
    from paragraf.providers.gemini import extract_json

    assert extract_json('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert extract_json('{"a": {"b": [1, 2]}}\n```') == '{"a": {"b": [1, 2]}}'
    assert extract_json("bez json") == "bez json"
