"""Tests for the Stop-hook reconcile gate decision logic."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.context import reconcile_gate as rg
from dummyindex.context.drift import DriftReport, DriftRow
from dummyindex.context.domains.memory.transcript import SessionSignal
from dummyindex.context.reconcile_gate import (
    auto_council_enabled,
    render_block,
)


def _write_cfg(root: Path, payload: dict) -> None:
    p = root / ".context" / "config.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload), encoding="utf-8")


# ----- auto_council_enabled -------------------------------------------------


def test_enabled_by_default_when_no_config(tmp_path: Path) -> None:
    assert auto_council_enabled(tmp_path) is True


def test_enabled_when_config_lacks_key(tmp_path: Path) -> None:
    _write_cfg(tmp_path, {"other": 1})
    assert auto_council_enabled(tmp_path) is True


def test_disabled_when_auto_council_false(tmp_path: Path) -> None:
    _write_cfg(tmp_path, {"auto_council": False})
    assert auto_council_enabled(tmp_path) is False


def test_enabled_when_config_malformed(tmp_path: Path) -> None:
    cfg = tmp_path / ".context" / "config.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text("{ not json", encoding="utf-8")
    assert auto_council_enabled(tmp_path) is True


# ----- render_block ---------------------------------------------------------


def test_render_block_lists_drifted_features_and_stamp() -> None:
    report = DriftReport(
        rows=(
            DriftRow(rel_path="a.py", feature_id="auth"),
            DriftRow(rel_path="b.py", feature_id="billing"),
        ),
        unassigned_new_files=("new/x.py",),
        awaiting_enrichment=("search",),
    )
    payload = render_block(report)
    obj = json.loads(payload)
    assert obj["decision"] == "block"
    reason = obj["reason"]
    assert "auth" in reason and "billing" in reason
    assert "new/x.py" in reason
    assert "search" in reason
    assert "reconcile-stamp" in reason
    assert "auto_council" in reason


# ----- decide_block ---------------------------------------------------------


@pytest.fixture
def patched(monkeypatch, tmp_path):
    state = {
        "enabled": True,
        "report": DriftReport(rows=(DriftRow(rel_path="a.py", feature_id="auth"),)),
        "signal": SessionSignal(
            output_tokens=50_000, subagent_file_count=0, main_turns=3
        ),
    }
    monkeypatch.setattr(rg, "auto_council_enabled", lambda root: state["enabled"])
    monkeypatch.setattr(rg, "compute_drift", lambda root: state["report"])
    monkeypatch.setattr(rg, "read_session_signal", lambda p: state["signal"])
    return state, tmp_path


def _transcript(root: Path) -> Path:
    t = root / "t.jsonl"
    t.write_text("{}", encoding="utf-8")
    return t


def test_blocks_when_drift_substantive_not_active(patched):
    state, root = patched
    out = rg.decide_block(
        root=root, main_transcript=_transcript(root), stop_hook_active=False
    )
    assert out is not None
    assert json.loads(out)["decision"] == "block"


def test_silent_when_stop_hook_active(patched):
    state, root = patched
    out = rg.decide_block(
        root=root, main_transcript=_transcript(root), stop_hook_active=True
    )
    assert out is None


def test_silent_when_opted_out(patched):
    state, root = patched
    state["enabled"] = False
    out = rg.decide_block(
        root=root, main_transcript=_transcript(root), stop_hook_active=False
    )
    assert out is None


def test_silent_when_no_drift(patched):
    state, root = patched
    state["report"] = DriftReport(rows=())
    out = rg.decide_block(
        root=root, main_transcript=_transcript(root), stop_hook_active=False
    )
    assert out is None


def test_silent_when_not_substantive(patched):
    state, root = patched
    state["signal"] = SessionSignal(
        output_tokens=10, subagent_file_count=0, main_turns=1
    )
    out = rg.decide_block(
        root=root, main_transcript=_transcript(root), stop_hook_active=False
    )
    assert out is None


def test_silent_when_no_transcript(patched):
    state, root = patched
    out = rg.decide_block(root=root, main_transcript=None, stop_hook_active=False)
    assert out is None
