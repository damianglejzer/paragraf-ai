"""HTTP client for the Sejm ELI API, written against docs/eli_openapi.yaml.

Endpoints used:
- GET /acts/search                                  -> `acts`
- GET /acts/{publisher}/{year}/{position}           -> `Act`
- GET /acts/{publisher}/{year}/{position}/text.html -> text/html
- GET /acts/{publisher}/{year}/{position}/struct    -> JSON tree

Raw responses for act texts are cached on disk; the API occasionally returns transient 5xx.
"""

import json
from pathlib import Path
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from paragraf.eli.models import Act, ActList


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500


class EliClient:
    def __init__(
        self,
        base_url: str = "https://api.sejm.gov.pl/eli",
        cache_dir: Path | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._http = httpx.Client(
            base_url=base_url,
            timeout=60.0,
            headers={"User-Agent": "paragraf-ai/0.1 (portfolio project)"},
            transport=transport,
        )
        self._cache_dir = cache_dir

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "EliClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, max=20),
        reraise=True,
    )
    def _get(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        resp = self._http.get(path, params=params)
        resp.raise_for_status()
        return resp

    def _cached(self, eli: str, endpoint: str, filename: str) -> bytes:
        """GET /acts/{eli}/{endpoint}, cached as <cache_dir>/<eli>/<filename>."""
        path = f"/acts/{eli}/{endpoint}"
        if self._cache_dir is not None:
            target = self._cache_dir / eli.replace("/", "_") / filename
            if target.exists():
                return target.read_bytes()
            content = self._get(path).content
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            return content
        return self._get(path).content

    def search(self, **params: str | int) -> ActList:
        """GET /acts/search with query parameters from the spec (title, type, publisher, ...)."""
        return ActList.model_validate(self._get("/acts/search", params=params).json())

    def get_act(self, eli: str) -> Act:
        """GET /acts/{publisher}/{year}/{position}; `eli` like 'DU/2023/1465'."""
        return Act.model_validate(self._get(f"/acts/{eli}").json())

    def get_text_html(self, eli: str) -> str:
        return self._cached(eli, "text.html", "text.html").decode("utf-8")

    def get_struct(self, eli: str) -> Any:
        return json.loads(self._cached(eli, "struct", "struct.json"))
