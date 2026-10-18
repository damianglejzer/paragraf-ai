from pathlib import Path

import pytest

from paragraf.parsing.html_parser import display_number, parse_act_html, structure_number
from paragraf.parsing.models import ActMeta, Provision

FIXTURE = Path(__file__).parent / "fixtures" / "mini_act.html"
ACT = ActMeta(code="KP", name="Kodeks pracy", eli="DU/2023/1465", title="Obwieszczenie")


@pytest.fixture(scope="module")
def provisions() -> dict[str, Provision]:
    return {p.id: p for p in parse_act_html(FIXTURE.read_text(encoding="utf-8"), ACT)}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("154", "154"), ("3_1", "3¹"), ("67_19", "67¹⁹"), ("101a", "101a"), ("109-157", "109–157")],
)
def test_display_number(raw: str, expected: str) -> None:
    assert display_number(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("SIÓDMY", "VII"),
        ("PIERWSZA", "I"),
        ("CZTERNASTY_a", "XIVa"),
        ("IIa", "IIa"),
        ("OGÓLNA", "ogólna"),
    ],
)
def test_structure_number(raw: str, expected: str) -> None:
    assert structure_number(raw) == expected


def test_only_statute_section_is_parsed(provisions: dict[str, Provision]) -> None:
    # art. 415 is quoted inside the announcement (part_1), art. 999 is in an annex (part_3)
    assert "KP:art_415" not in provisions
    assert "KP:art_999" not in provisions


def test_full_path_and_citation(provisions: dict[str, Provision]) -> None:
    p = provisions["KP:art_154:par_1"]
    assert p.full_path == "KP, Dział VII, Rozdział I, art. 154 § 1"
    assert p.citation == "art. 154 § 1 KP"
    assert p.hierarchy_titles == ["Urlopy pracownicze", "Urlopy wypoczynkowe"]
    assert p.parent_id == "KP:art_154"
    assert p.level == "paragraph"


def test_points_are_folded_into_paragraph(provisions: dict[str, Provision]) -> None:
    text = provisions["KP:art_154:par_1"].text
    assert text.splitlines() == [
        "Wymiar urlopu wynosi:",
        "1) 20 dni - jeżeli pracownik jest zatrudniony krócej niż 10 lat;",
        "2) 26 dni - jeżeli pracownik jest zatrudniony co najmniej 10 lat.",
    ]


def test_article_with_paragraphs_is_not_a_chunk(provisions: dict[str, Provision]) -> None:
    article = provisions["KP:art_154"]
    assert not article.is_chunk
    assert "§ 1. Wymiar urlopu wynosi:" in article.text


def test_empty_unit_number_falls_back_to_bookmark(provisions: dict[str, Provision]) -> None:
    assert "KP:art_154:par_2" in provisions


def test_repealed_units_are_flagged_and_not_chunks(provisions: dict[str, Provision]) -> None:
    assert provisions["KP:art_154:par_3"].repealed
    assert not provisions["KP:art_154:par_3"].is_chunk
    article_range = provisions["KP:art_109-157"]
    assert article_range.repealed
    assert article_range.article == "109–157"


def test_superscripts_and_noise_are_cleaned(provisions: dict[str, Provision]) -> None:
    p = provisions["KP:art_3_1"]
    assert p.article == "3¹"
    assert p.is_chunk
    assert "art. 22¹ § 1" in p.text
    assert "Dz. U." not in p.text  # hidden metadata removed


def test_duplicate_wording_keeps_latest(provisions: dict[str, Provision]) -> None:
    assert provisions["KP:art_107"].text == "Nowe brzmienie, grzywna."


def test_order_is_sequential(provisions: dict[str, Provision]) -> None:
    orders = sorted(p.order for p in provisions.values())
    assert orders == list(range(len(orders)))
