"""Query rewriting: translate a layperson's question into statutory vocabulary.

Statutes say "umowa zawarta na odległość" where users say "sklep internetowy". Rewriting
closes that vocabulary gap for both full-text and vector search (docs/DECISIONS.md, D10).
"""

from paragraf.providers.base import LLM, ProviderUnavailable

REWRITE_SYSTEM = (
    "Przepisz pytanie laika na jedno zwięzłe zapytanie wyszukiwawcze w języku polskich ustaw "
    "(terminy prawne, nazwy instytucji prawnych). Nie odpowiadaj na pytanie. Nie dodawaj "
    "numerów artykułów. Jeśli pytanie nie dotyczy prawa, przepisz je bez zmian. "
    "Zwróć wyłącznie zapytanie."
)


class QueryRewriter:
    def __init__(self, llm: LLM) -> None:
        self._llm = llm

    def __call__(self, question: str) -> str | None:
        """Rewritten query, or None when the LLM is unavailable (search falls back to original)."""
        try:
            text = self._llm.complete(REWRITE_SYSTEM, question).text.strip()
        except ProviderUnavailable:
            return None
        return text[:500] or None
