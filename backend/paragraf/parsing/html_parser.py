"""Structural parser for ELI HTML consolidated texts.

The HTML nests `div.unit.unit_<type>` elements whose `data-id` is `<type>_<name>`, e.g.
`arti_154` > `para_1` > `pint_2`. The consolidated statute lives in the `<section>` whose
heading contains "Tekst jednolity"; the announcement itself and annexes are skipped.
"""

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag

from paragraf.parsing.models import ActMeta, Provision

SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
STRUCTURE_LABELS = {
    "book": "Księga",
    "part": "Część",
    "titl": "Tytuł",
    "bran": "Dział",
    "chpt": "Rozdział",
    "schp": "Oddział",
}
ORDINALS = {
    "PIERWSZ": "I",
    "DRUG": "II",
    "TRZECI": "III",
    "CZWART": "IV",
    "PIĄT": "V",
    "SZÓST": "VI",
    "SIÓDM": "VII",
    "ÓSM": "VIII",
    "DZIEWIĄT": "IX",
    "DZIESIĄT": "X",
    "JEDENAST": "XI",
    "DWUNAST": "XII",
    "TRZYNAST": "XIII",
    "CZTERNAST": "XIV",
    "PIĘTNAST": "XV",
}
REPEALED_RE = re.compile(r"^\(?(uchylon[yae]|pominięt[yae]|skreślon[yae])\)?\.?$", re.IGNORECASE)


def normalize_ws(text: str) -> str:
    text = re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
    # superscripts were separate tags: "art. 36 ¹ §1" -> "art. 36¹ § 1"
    text = re.sub(r"\s+([⁰¹²³⁴⁵⁶⁷⁸⁹]+)", r"\1", text)
    return re.sub(r"§(?=\d)", "§ ", text)


def display_number(name: str) -> str:
    """'101_1' -> '101¹', '101a' -> '101a', '109-157' -> '109–157'."""
    if "-" in name:
        return "–".join(display_number(p) for p in name.split("-"))
    base, *sups = name.split("_")
    return base + "".join(s.translate(SUPERSCRIPT) if s.isdecimal() else s for s in sups)


def structure_number(name: str) -> str:
    """Ordinal words ('SIÓDMY', 'CZTERNASTY_a') -> Roman numerals ('VII', 'XIVa')."""
    base, *rest = name.split("_")
    for prefix, roman in ORDINALS.items():
        if base.upper().startswith(prefix):
            base = roman
            break
    else:
        if base in {"OGÓLNA", "SZCZEGÓLNA", "WOJSKOWA"}:
            base = base.lower()
    return base + "".join(r.translate(SUPERSCRIPT) if r.isdecimal() else r for r in rest)


def unit_type(tag: Tag) -> str | None:
    for cls in tag.get("class") or []:
        if cls.startswith("unit_"):
            return str(cls[5:])
    return None


def unit_name(tag: Tag, position: int | None = None) -> str:
    """Unit number from `data-id` ('para_2_1' -> '2_1').

    Some source units have an empty number ('para_'); fall back to the bookmark suffix
    ('..._p1') and then to the 1-based position among siblings.
    """
    data_id = str(tag.get("data-id", ""))
    name = data_id.split("_", 1)[1] if "_" in data_id else data_id
    if name:
        return name
    bookmark = re.search(r"_[a-z](\d+)$", str(tag.get("data-bookmark", "")))
    if bookmark:
        return bookmark.group(1)
    return str(position) if position is not None else "0"


def _clean(soup: BeautifulSoup) -> None:
    for sel in ("a.gloss-link", "span.xHidden", "div.gloss-section", "span.tooltip-text"):
        for el in soup.select(sel):
            el.decompose()
    for sup in soup.find_all(["sup", "SUP"]):
        sup.replace_with(sup.get_text().strip().translate(SUPERSCRIPT))


def _inner(unit: Tag) -> Tag | None:
    inner = unit.find("div", class_="unit-inner", recursive=False)
    return inner if isinstance(inner, Tag) else None


def _heading(unit: Tag) -> str:
    h3 = unit.find("h3", recursive=False)
    return normalize_ws(h3.get_text(" ")) if isinstance(h3, Tag) else ""


def render_text(unit: Tag) -> str:
    """Text of a unit without its own heading; nested units become labelled lines."""
    inner = _inner(unit)
    if inner is None:
        return ""
    lines: list[str] = []
    for child in inner.children:
        if not isinstance(child, Tag):
            continue
        if unit_type(child) is not None:
            label = _heading(child)
            body = render_text(child)
            lines.append(f"{label} {body}".strip())
        else:
            text = normalize_ws(child.get_text(" "))
            if text:
                lines.append(text)
    return "\n".join(lines)


def child_units(tag: Tag) -> list[Tag]:
    """Nearest `div.unit` descendants of `tag`, not descending into units or quoted text."""
    found: list[Tag] = []
    for child in tag.children:
        if not isinstance(child, Tag):
            continue
        classes = child.get("class") or []
        if "cite-box" in classes:
            continue
        if child.name == "div" and "unit" in classes:
            found.append(child)
        else:
            found.extend(child_units(child))
    return found


def _structure_title(unit: Tag) -> str:
    title = unit.find("span", class_="pro-title-unit")
    return normalize_ws(title.get_text(" ")) if isinstance(title, Tag) else ""


@dataclass
class _Ctx:
    hierarchy: list[str] = field(default_factory=list)
    titles: list[str] = field(default_factory=list)


def _find_statute_section(soup: BeautifulSoup) -> Tag:
    for section in soup.find_all("section"):
        h2 = section.find("h2")
        if (
            isinstance(section, Tag)
            and isinstance(h2, Tag)
            and "tekst jednolity" in h2.get_text(" ").lower()
        ):
            return section
    raise ValueError("no 'Tekst jednolity' section found in HTML")


def parse_act_html(html: str, act: ActMeta) -> list[Provision]:
    soup = BeautifulSoup(html, "lxml")
    _clean(soup)
    section = _find_statute_section(soup)
    provisions: list[Provision] = []

    def visit(container: Tag, ctx: _Ctx) -> None:
        for child in child_units(container):
            kind = unit_type(child)
            if kind in STRUCTURE_LABELS:
                label = f"{STRUCTURE_LABELS[kind]} {structure_number(unit_name(child))}"
                sub = _Ctx([*ctx.hierarchy, label], [*ctx.titles, _structure_title(child)])
                visit(child, sub)
            elif kind == "arti":
                _emit_article(child, ctx, act, provisions)

    visit(section, _Ctx())
    return [p.model_copy(update={"order": i}) for i, p in enumerate(provisions)]


def _emit_article(unit: Tag, ctx: _Ctx, act: ActMeta, out: list[Provision]) -> None:
    name = unit_name(unit)
    art_display = display_number(name)
    art_id = f"{act.code}:art_{name}"
    hierarchy_path = ", ".join([act.code, *ctx.hierarchy])
    subunits = [c for c in child_units(unit) if unit_type(c) in ("para", "pass")]
    # Consolidated texts sometimes contain two wordings of the same unit: the current one
    # ("W tym brzmieniu obowiązuje do wejścia w życie zmiany...") followed by the future one.
    # Our texts are 1-3 years old, so the later wording is the one in force: keep the last.
    out[:] = [p for p in out if p.id != art_id and p.parent_id != art_id]
    text = render_text(unit)
    repealed = bool(REPEALED_RE.match(text.strip())) or not text.strip()
    out.append(
        Provision(
            id=art_id,
            act_code=act.code,
            level="article",
            article=art_display,
            hierarchy=ctx.hierarchy,
            hierarchy_titles=ctx.titles,
            citation=f"art. {art_display} {act.code}",
            full_path=f"{hierarchy_path}, art. {art_display}",
            text=text or "(uchylony)",
            repealed=repealed,
            is_chunk=not subunits and not repealed,
            order=len(out),
        )
    )
    for position, sub in enumerate(subunits, start=1):
        kind = unit_type(sub)
        sub_name = unit_name(sub, position)
        sub_display = display_number(sub_name)
        unit_label = f"§ {sub_display}" if kind == "para" else f"ust. {sub_display}"
        sub_text = render_text(sub) or "(uchylony)"
        sub_repealed = bool(REPEALED_RE.match(sub_text.strip()))
        prefix = "par" if kind == "para" else "ust"
        sub_id = f"{art_id}:{prefix}_{sub_name}"
        out[:] = [p for p in out if p.id != sub_id]
        out.append(
            Provision(
                id=sub_id,
                act_code=act.code,
                level="paragraph" if kind == "para" else "passage",
                article=art_display,
                unit=unit_label,
                parent_id=art_id,
                hierarchy=ctx.hierarchy,
                hierarchy_titles=ctx.titles,
                citation=f"art. {art_display} {unit_label} {act.code}",
                full_path=f"{hierarchy_path}, art. {art_display} {unit_label}",
                text=sub_text,
                repealed=sub_repealed,
                is_chunk=not sub_repealed,
                order=len(out),
            )
        )
