"""Runs against the local Postgres after `python -m paragraf.ingest` (pytest -m integration)."""

import pytest

from paragraf.db import repository as repo

pytestmark = pytest.mark.integration


def test_known_provision_is_stored() -> None:
    with repo.connect() as conn:
        row = repo.get_provision(conn, "KP:art_154:par_1")
        assert row is not None
        assert row["full_path"] == "KP, Dział VII, Rozdział I, art. 154 § 1"
        assert "20 dni" in row["text"]


def test_unknown_unit_falls_back_to_article() -> None:
    with repo.connect() as conn:
        row = repo.get_provision(conn, "KP:art_154:par_99")
        assert row is not None
        assert row["id"] == "KP:art_154"


def test_children_and_references() -> None:
    with repo.connect() as conn:
        children = repo.get_children(conn, "KP:art_154")
        assert [c["unit"] for c in children][:2] == ["§ 1", "§ 2"]
        assert "KP:art_154:par_1" in repo.get_outgoing_references(conn, "KP:art_154:par_2")
