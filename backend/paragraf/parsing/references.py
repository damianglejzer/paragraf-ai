"""Extract cross-references ("art. 22 § 1", "art. 5 Kodeksu cywilnego") from provision text.

Only references that resolve to an act in our corpus are kept: same-act references, and
references naming one of the indexed statutes. References to other acts are skipped.
"""

import re

from paragraf.parsing.models import CrossReference, Provision

FROM_SUPERSCRIPT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
SUP = "⁰¹²³⁴⁵⁶⁷⁸⁹"

# The genitive form used after "art. N ..." -> act code
KNOWN_ACTS: dict[str, str] = {
    "kodeksu cywilnego": "KC",
    "kodeksu pracy": "KP",
    "kodeksu rodzinnego i opiekuńczego": "KRO",
    "kodeksu wykroczeń": "KW",
    "ordynacji podatkowej": "OP",
    "ustawy o prawach konsumenta": "UPK",
    "ustawy o ochronie danych osobowych": "ODO",
}
# Anything that names a different act right after the reference
FOREIGN_ACT_RE = re.compile(
    r"^\s*(ustaw[yaie]|rozporządze|kodeksu|konstytucji|dyrektyw|traktatu|umowy|przepisów)",
    re.IGNORECASE,
)

NUM = rf"\d+[a-z]{{0,3}}[{SUP}]*[a-z]{{0,2}}"
UNIT = rf"(?:§\s*(?P<par>{NUM})|ust\.\s*(?P<ust>{NUM}))"
REF_RE = re.compile(
    rf"\bart\.\s*(?P<art>{NUM})(?:\s*[-–]\s*(?P<art_to>{NUM}))?(?:\s+{UNIT})?",
)
# Further articles in a list: "art. 132 i 133", "art. 114-116 i 118", "art. 22, 23 oraz 24"
MORE_RE = re.compile(rf"^(?:\s*(?:,|i|oraz|lub|albo)\s+)(?P<art>{NUM})(?![\s]*(?:§|ust\.|pkt))")


# Bare unit references inside the same article: "w § 1 i 2", "o którym mowa w ust. 3"
LOCAL_RE = re.compile(rf"(?P<kind>§|ust\.)\s*(?P<num>{NUM})")
LOCAL_MORE_RE = re.compile(rf"^\s*(?:,|i|oraz|lub|albo)\s+(?P<num>{NUM})(?!\s*(?:pkt|ust\.|§))")


def to_id_number(display: str) -> str:
    """'36¹' -> '36_1', '67¹⁹' -> '67_19', '22a' -> '22a', '22¹c' -> '22_1_c' (ELI data-id form)."""
    match = re.match(rf"^(\d+[a-z]*)([{SUP}]*)([a-z]*)$", display)
    if not match:
        return display
    base, sup, suffix = match.groups()
    out = base
    if sup:
        out += "_" + sup.translate(FROM_SUPERSCRIPT)
        if suffix:
            out += "_"
    return out + suffix


def _target_act(after: str, own_act: str) -> str | None:
    lowered = after.lower().lstrip(" ,")
    for name, code in KNOWN_ACTS.items():
        if lowered.startswith(name):
            return code
    if FOREIGN_ACT_RE.match(lowered):
        return None
    return own_act


def _expand_range(start: str, end: str) -> list[str]:
    if start.isdecimal() and end.isdecimal() and 0 < int(end) - int(start) <= 20:
        return [str(n) for n in range(int(start), int(end) + 1)]
    return [start, end]


def extract_references(provision: Provision) -> list[CrossReference]:
    text = provision.text
    refs: dict[str, CrossReference] = {}
    for match in REF_RE.finditer(text):
        articles = (
            _expand_range(match["art"], match["art_to"]) if match["art_to"] else [match["art"]]
        )
        unit: str | None = None
        if match["par"]:
            unit = f"par_{to_id_number(match['par'])}"
        elif match["ust"]:
            unit = f"ust_{to_id_number(match['ust'])}"
        end = match.end()
        if unit is None:
            while more := MORE_RE.match(text[end:]):
                articles.append(more["art"])
                end += more.end()
        after = re.sub(r"^(\s*(pkt|zdanie|lit\.)\s*\S+)+", "", text[end : end + 120])
        target_act = _target_act(after, provision.act_code)
        if target_act is None:
            continue
        for art in articles:
            ref = CrossReference(
                source_id=provision.id,
                target_act=target_act,
                target_article=to_id_number(art),
                target_unit=unit if len(articles) == 1 else None,
                raw=match.group(0),
            )
            if ref.target_id != provision.id and ref.target_id != provision.parent_id:
                refs.setdefault(ref.target_id, ref)
    refs.update({r.target_id: r for r in _local_references(provision) if r.target_id not in refs})
    return list(refs.values())


def _local_references(provision: Provision) -> list[CrossReference]:
    """'§ 1' / 'ust. 2' not preceded by 'art. N' point into the provision's own article."""
    text = provision.text
    covered = [m.span() for m in REF_RE.finditer(text)]
    article_id = provision.parent_id or provision.id
    article_number = article_id.split(":art_", 1)[1]
    out: list[CrossReference] = []
    for match in LOCAL_RE.finditer(text):
        if any(start <= match.start() < end for start, end in covered):
            continue
        prefix = "par" if match["kind"] == "§" else "ust"
        numbers = [match["num"]]
        end = match.end()
        while more := LOCAL_MORE_RE.match(text[end:]):
            numbers.append(more["num"])
            end += more.end()
        after = re.sub(r"^(\s*(pkt|zdanie|lit\.)\s*\S+)+", "", text[end : end + 120])
        if FOREIGN_ACT_RE.match(after.lower().lstrip(" ,")):
            continue
        for num in numbers:
            ref = CrossReference(
                source_id=provision.id,
                target_act=provision.act_code,
                target_article=article_number,
                target_unit=f"{prefix}_{to_id_number(num)}",
                raw=match.group(0),
            )
            if ref.target_id != provision.id:
                out.append(ref)
    return out
