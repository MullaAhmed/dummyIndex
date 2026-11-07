"""Checklist live-step lint: ``live_items``."""

from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.context.domains.buildloop.checklist import parse_checklist
from dummyindex.context.domains.buildloop.checklist_lint import live_items

pytestmark = pytest.mark.unit


def _parse(tmp_path: Path, lines: list[str]):
    path = tmp_path / "checklist.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return parse_checklist(path)


POSITIVES = [
    "Run live tests against the service",
    "Do a production smoke check",
    "Manually verify the output",
    "Hit staging: run against staging",
    "Call the real API and compare",
]
NEGATIVES = [
    "Enable live-reload in dev server",
    "Fix delivery of the report",
    "Keep production-grade logging",
    "Entries stay live in the index",
    "Add a test named smoke for the CLI",
]


def test_positives_flagged(tmp_path: Path) -> None:
    items = _parse(tmp_path, [f"- [ ] {t}" for t in POSITIVES])
    assert [i.text for i in live_items(items)] == POSITIVES


def test_negatives_ignored(tmp_path: Path) -> None:
    items = _parse(tmp_path, [f"- [ ] {t}" for t in NEGATIVES])
    assert live_items(items) == ()


def test_live_ok_honoured(tmp_path: Path) -> None:
    items = _parse(
        tmp_path,
        ["- [ ] Run live tests <!-- live-ok: fixture replay, no network -->"],
    )
    assert "live-ok" in items[0].text
    assert live_items(items) == ()


def test_ticked_ignored(tmp_path: Path) -> None:
    items = _parse(
        tmp_path, ["- [x] Run live tests", "- [~] Manual test — skipped: n/a"]
    )
    assert live_items(items) == ()
