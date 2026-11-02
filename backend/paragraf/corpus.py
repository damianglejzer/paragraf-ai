"""Corpus scope: which statutes and which parts of them are indexed.

The Labour Code is indexed in full: it is the app's main subject (docs/DECISIONS.md, D18). The
other acts keep a few everyday topics from the original demo (D9). Widening the scope means
adding entries here and re-running ingest + index.
"""

# act code -> hierarchy prefixes to keep (a provision is kept if its hierarchy starts with one;
# the empty prefix keeps the whole act)
CORPUS_SCOPE: dict[str, list[tuple[str, ...]]] = {
    "KP": [()],
    "UPK": [
        ("Rozdział 1",),  # Przepisy ogólne
        ("Rozdział 3",),  # Umowy na odległość i poza lokalem: obowiązki informacyjne
        ("Rozdział 4",),  # Prawo odstąpienia od umowy (zwrot w 14 dni)
        ("Rozdział 5a",),  # Niezgodność towaru z umową
    ],
    "KC": [
        ("Księga I", "Część ogólna", "Tytuł V"),  # Terminy
        ("Księga I", "Część ogólna", "Tytuł VI"),  # Przedawnienie roszczeń
        ("Księga III", "Tytuł XVII", "Dział I"),  # Najem
    ],
}

TOPICS = [
    "cały Kodeks pracy",
    "zwrot towaru kupionego przez internet",
    "reklamacja towaru niezgodnego z umową",
    "najem mieszkania",
    "przedawnienie roszczeń cywilnych",
]


def in_scope(act_code: str, hierarchy: list[str]) -> bool:
    prefixes = CORPUS_SCOPE.get(act_code)
    if prefixes is None:
        return False
    return any(tuple(hierarchy[: len(p)]) == p for p in prefixes)
