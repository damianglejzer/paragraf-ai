import pytest

from paragraf.parsing.models import Provision
from paragraf.parsing.references import extract_references, to_id_number


def make(text: str, pid: str = "KP:art_10", act: str = "KP") -> Provision:
    return Provision(
        id=pid,
        act_code=act,
        level="article",
        article="10",
        citation="art. 10 KP",
        full_path="KP, art. 10",
        text=text,
        is_chunk=True,
        order=0,
    )


def targets(text: str, **kw: str) -> list[str]:
    return sorted(r.target_id for r in extract_references(make(text, **kw)))


@pytest.mark.parametrize(
    ("display", "expected"),
    [("36¹", "36_1"), ("67¹⁹", "67_19"), ("22a", "22a"), ("22¹c", "22_1_c"), ("154", "154")],
)
def test_to_id_number(display: str, expected: str) -> None:
    assert to_id_number(display) == expected


def test_same_act_reference_with_paragraph() -> None:
    assert targets("Przepis art. 154 § 1 stosuje się odpowiednio.") == ["KP:art_154:par_1"]


def test_passage_reference() -> None:
    assert targets("o którym mowa w art. 5 ust. 2,", pid="ODO:art_1", act="ODO") == [
        "ODO:art_5:ust_2"
    ]


def test_list_and_range_of_articles() -> None:
    assert targets("Przepisy art. 114-116 i 118 stosuje się.") == [
        "KP:art_114",
        "KP:art_115",
        "KP:art_116",
        "KP:art_118",
    ]


def test_superscript_article() -> None:
    assert targets("zgodnie z art. 22¹ § 3") == ["KP:art_22_1:par_3"]


def test_reference_to_other_indexed_act() -> None:
    assert targets("stosuje się art. 5 Kodeksu cywilnego.") == ["KC:art_5"]


def test_reference_to_unindexed_act_is_skipped() -> None:
    assert targets("art. 4 ust. 3 ustawy z dnia 4 listopada 2016 r. o wsparciu kobiet") == []


def test_self_reference_is_skipped() -> None:
    assert targets("art. 10 stosuje się.") == []


def test_local_unit_references_point_into_own_article() -> None:
    p = make("ustalony na podstawie § 1 i 2, nie może przekroczyć", pid="KP:art_154:par_3")
    p = p.model_copy(update={"parent_id": "KP:art_154", "level": "paragraph"})
    assert sorted(r.target_id for r in extract_references(p)) == [
        "KP:art_154:par_1",
        "KP:art_154:par_2",
    ]


def test_unit_after_article_is_not_treated_as_local() -> None:
    assert targets("zgodnie z art. 30 § 4") == ["KP:art_30:par_4"]
