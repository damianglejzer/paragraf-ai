import math

from paragraf.evaluation.metrics import (
    article_of,
    is_relevant,
    percentile,
    recall_at_k,
    reciprocal_rank,
)


def test_article_of() -> None:
    assert article_of("KP:art_154:par_1") == "KP:art_154"
    assert article_of("KP:art_154") == "KP:art_154"


def test_article_level_relevance_accepts_sibling_unit() -> None:
    assert is_relevant(["KP:art_154:par_2"], "KP:art_154:par_1")
    assert not is_relevant(["KP:art_154:par_2"], "KP:art_154:par_1", level="unit")
    assert not is_relevant(["KP:art_15"], "KP:art_154")  # no prefix confusion


def test_recall_at_k_with_multi_provision_question() -> None:
    ranked = [["KP:art_1"], ["KC:art_5"], ["KP:art_154:par_1"]]
    expected = ["KP:art_154:par_1", "KP:art_155"]
    assert recall_at_k(ranked, expected, 2) == 0.0
    assert recall_at_k(ranked, expected, 3) == 0.5


def test_naive_hits_cover_several_provisions() -> None:
    ranked = [["KP:art_153", "KP:art_154:par_1", "KP:art_154:par_2"]]
    assert recall_at_k(ranked, ["KP:art_154:par_2"], 1, level="unit") == 1.0


def test_reciprocal_rank() -> None:
    ranked = [["A:art_1"], ["A:art_2"], ["A:art_3"]]
    assert reciprocal_rank(ranked, ["A:art_2"]) == 0.5
    assert reciprocal_rank(ranked, ["A:art_9"]) == 0.0
    assert math.isnan(reciprocal_rank(ranked, []))


def test_percentile() -> None:
    values = [float(v) for v in range(1, 101)]
    assert percentile(values, 50) == 50.0
    assert percentile(values, 95) == 95.0
