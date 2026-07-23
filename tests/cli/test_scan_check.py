"""`dummyindex context scan-check` — the authoring loop's feedback command.

This is what makes a model-authored `features/graph.json` self-correcting:
the author writes the scan, runs one command, and gets back every violation
with a JSON path. Exit codes carry the same answer for scripts — `0` clean,
`1` violations, `2` nothing to check.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.cli import dispatch
from dummyindex.context.domains.features.constants import SCAN_SCHEMA_VERSION


def _write_scan(tmp_path: Path, payload: object) -> Path:
    features = tmp_path / ".context" / "features"
    features.mkdir(parents=True)
    (features / "graph.json").write_text(json.dumps(payload), encoding="utf-8")
    return tmp_path


def _valid() -> dict:
    return {
        "schema_version": SCAN_SCHEMA_VERSION,
        "project": {"name": "Acme", "slug": "acme"},
        "stats": {"agents": 0, "models": 0, "tools": 0, "integrations": 0},
        "topModels": [],
        "topTools": [],
        "topIntegrations": [],
        "graph": {
            "nodes": [{"id": "a", "label": "A", "kind": "service"}],
            "edges": [],
        },
        "confidence": "INFERRED",
    }


@pytest.mark.integration
def test_clean_scan_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(_write_scan(tmp_path, _valid()))
    assert dispatch(["scan-check"]) == 0
    assert "ok" in capsys.readouterr().out.lower()


@pytest.mark.integration
def test_violations_exit_one_and_name_the_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = _valid()
    payload["graph"]["nodes"][0]["kind"] = "microservice"
    monkeypatch.chdir(_write_scan(tmp_path, payload))

    assert dispatch(["scan-check"]) == 1

    err = capsys.readouterr().err
    assert "graph.nodes[0].kind" in err
    assert "node_kind" in err


@pytest.mark.integration
def test_reports_every_violation_in_one_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """One round trip, not one per mistake — that's the whole point."""
    payload = _valid()
    payload["graph"]["nodes"][0]["kind"] = "nope"
    payload["graph"]["nodes"].append({"id": "b", "label": "x" * 40, "kind": "store"})
    payload["graph"]["edges"].append({"from": "a", "to": "ghost"})
    monkeypatch.chdir(_write_scan(tmp_path, payload))

    assert dispatch(["scan-check"]) == 1

    err = capsys.readouterr().err
    for code in ("node_kind", "node_label_length", "edge_endpoint"):
        assert code in err


@pytest.mark.integration
def test_json_output_is_machine_readable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = _valid()
    payload["graph"]["nodes"][0]["kind"] = "nope"
    monkeypatch.chdir(_write_scan(tmp_path, payload))

    assert dispatch(["scan-check", "--json"]) == 1

    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is False
    assert report["violations"][0]["code"] == "node_kind"
    assert report["violations"][0]["path"] == "graph.nodes[0].kind"


@pytest.mark.integration
def test_missing_scan_is_a_usage_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".context").mkdir()
    monkeypatch.chdir(tmp_path)
    assert dispatch(["scan-check"]) == 2
    assert "graph.json" in capsys.readouterr().err


@pytest.mark.integration
def test_unparseable_scan_is_a_usage_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    features = tmp_path / ".context" / "features"
    features.mkdir(parents=True)
    (features / "graph.json").write_text("{ nope", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert dispatch(["scan-check"]) == 2
    assert "json" in capsys.readouterr().err.lower()


@pytest.mark.integration
def test_seeded_scan_is_reported_as_uncurated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A valid seed passes, but the author still needs to know it's a seed."""
    payload = _valid()
    payload["confidence"] = "EXTRACTED"
    monkeypatch.chdir(_write_scan(tmp_path, payload))

    assert dispatch(["scan-check"]) == 0
    assert "EXTRACTED" in capsys.readouterr().out


@pytest.mark.integration
def test_rejects_unknown_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(_write_scan(tmp_path, _valid()))
    assert dispatch(["scan-check", "--bogus"]) == 2
    assert "--bogus" in capsys.readouterr().err


@pytest.mark.integration
def test_help_prints_usage_without_reading_anything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)  # no .context at all
    assert dispatch(["scan-check", "--help"]) == 0
    assert "scan-check" in capsys.readouterr().out
