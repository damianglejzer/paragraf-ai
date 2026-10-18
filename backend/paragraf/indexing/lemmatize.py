"""Polish lemmatization with spaCy `pl_core_news_sm` (tagger + lemmatizer only).

Lemmas are stored as plain text and indexed by Postgres with the 'simple' configuration,
because Postgres ships no Polish stemmer/dictionary. See docs/DECISIONS.md (D8).
"""

import re
from collections.abc import Iterable
from functools import lru_cache

import spacy
from spacy.language import Language

_KEEP_POS = {"NOUN", "PROPN", "VERB", "ADJ", "ADV", "NUM", "X", "AUX"}
_WORD = re.compile(r"^[\wąćęłńóśźż]+$", re.IGNORECASE)
# High-frequency words in statutes that carry no retrieval signal
LEGAL_STOPWORDS = {"być", "który", "ten", "się", "mowa", "przepis", "stosować", "odpowiednio"}


@lru_cache(maxsize=1)
def nlp() -> Language:
    return spacy.load("pl_core_news_sm", exclude=["parser", "ner", "senter"])


def _lemmas(doc: Iterable[spacy.tokens.Token]) -> list[str]:
    out: list[str] = []
    for tok in doc:
        if tok.is_punct or tok.is_space or not _WORD.match(tok.text):
            continue
        lemma = tok.lemma_.lower()
        if tok.is_stop or lemma in LEGAL_STOPWORDS or tok.pos_ not in _KEEP_POS:
            continue
        out.append(lemma)
    return out


def lemmatize(text: str) -> list[str]:
    return _lemmas(nlp()(text))


def lemmatize_many(texts: list[str], batch_size: int = 64) -> list[list[str]]:
    return [_lemmas(doc) for doc in nlp().pipe(texts, batch_size=batch_size)]
