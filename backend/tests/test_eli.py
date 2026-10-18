import datetime as dt
from pathlib import Path

import httpx

from paragraf.eli.client import EliClient
from paragraf.eli.discovery import is_consolidated_text_of, pick_newest_html
from paragraf.eli.models import ActInfo

TJ = "Obwieszczenie Marszałka Sejmu RP z dnia {d} w sprawie ogłoszenia jednolitego tekstu ustawy"


def act(pos: int, title: str, html: bool, year: int, type_: str = "Obwieszczenie") -> ActInfo:
    return ActInfo.model_validate(
        {
            "ELI": f"DU/{year}/{pos}",
            "address": f"WDU{year}{pos:07d}",
            "publisher": "DU",
            "year": year,
            "pos": pos,
            "title": title,
            "type": type_,
            "textHTML": html,
            "announcementDate": dt.date(year, 1, 1).isoformat(),
        }
    )


def test_consolidated_text_title_matching() -> None:
    assert is_consolidated_text_of(act(1, f"{TJ} - Kodeks pracy", True, 2023), "Kodeks pracy")
    # different statute whose name merely contains the target name
    assert not is_consolidated_text_of(
        act(2, f"{TJ} - Kodeks pracy morskiej", True, 2023), "Kodeks pracy"
    )
    # an amending statute, not a consolidated text
    assert not is_consolidated_text_of(
        act(3, "Ustawa o zmianie ustawy - Kodeks pracy", True, 2023, "Ustawa"), "Kodeks pracy"
    )


def test_pick_newest_with_html_skips_pdf_only() -> None:
    candidates = [
        act(10, f"{TJ} - Kodeks pracy", True, 2020),
        act(20, f"{TJ} - Kodeks pracy", True, 2023),
        act(30, f"{TJ} - Kodeks pracy", False, 2026),  # newest, but PDF only
    ]
    chosen = pick_newest_html(candidates, "Kodeks pracy")
    assert chosen is not None
    assert chosen.eli == "DU/2023/20"


def test_client_retries_transient_500_and_caches(tmp_path: Path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if len(calls) == 1:
            return httpx.Response(500)
        return httpx.Response(200, text="<html>ok</html>")

    client = EliClient(cache_dir=tmp_path, transport=httpx.MockTransport(handler))
    client._get.retry.wait = lambda *_: 0  # type: ignore[attr-defined]
    assert client.get_text_html("DU/2023/1465") == "<html>ok</html>"
    assert client.get_text_html("DU/2023/1465") == "<html>ok</html>"  # served from cache
    assert calls == ["/eli/acts/DU/2023/1465/text.html"] * 2
    assert (tmp_path / "DU_2023_1465" / "text.html").exists()
