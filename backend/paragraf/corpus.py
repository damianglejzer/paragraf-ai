"""Demo corpus scope: which statutes and which parts of them are indexed.

The demo deliberately covers a small set of everyday topics, so that indexing and evaluation fit
within free API quotas and the app stays fast (docs/DECISIONS.md, D9). The parser handles whole
statutes; widening the scope means adding entries here and re-running ingest + index.
"""

# act code -> hierarchy prefixes to keep (a provision is kept if its hierarchy starts with one)
CORPUS_SCOPE: dict[str, list[tuple[str, ...]]] = {
    "KP": [
        ("Dział II",),  # Stosunek pracy: umowy, wypowiedzenie, rozwiązanie umowy
        ("Dział VI",),  # Czas pracy, nadgodziny
        ("Dział VII",),  # Urlopy pracownicze
        ("Dział XIV",),  # Przedawnienie roszczeń
    ],
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
    "umowa o pracę i wypowiedzenie",
    "czas pracy i nadgodziny",
    "urlop wypoczynkowy",
    "zwrot towaru kupionego przez internet",
    "reklamacja towaru niezgodnego z umową",
    "najem mieszkania",
    "przedawnienie roszczeń",
    "obliczanie terminów",
]


def in_scope(act_code: str, hierarchy: list[str]) -> bool:
    prefixes = CORPUS_SCOPE.get(act_code)
    if prefixes is None:
        return False
    return any(tuple(hierarchy[: len(p)]) == p for p in prefixes)
