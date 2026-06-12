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


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _mk_index(root: Path) -> None:
    """Give ``root`` the shape ``discover_context_roots`` looks for."""
    (root / ".context" / "features").mkdir(parents=True, exist_ok=True)


def _declare_submodule(root: Path, name: str, rel: str) -> Path:
    _write(root / ".gitmodules", f'[submodule "{name}"]\n\tpath = {rel}\n')
    return root / rel


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


# ----- discover_context_roots -----------------------------------------------


def test_discover_root_only_when_no_submodules(tmp_path: Path) -> None:
    assert rg.discover_context_roots(tmp_path) == (tmp_path.resolve(),)


def test_discover_includes_submodule_with_index(tmp_path: Path) -> None:
    be = _declare_submodule(tmp_path, "backend", "backend")
    _mk_index(be)
    assert rg.discover_context_roots(tmp_path) == (
        tmp_path.resolve(),
        be.resolve(),
    )


def test_discover_skips_submodule_without_index(tmp_path: Path) -> None:
    be = _declare_submodule(tmp_path, "backend", "backend")
    be.mkdir()
    assert rg.discover_context_roots(tmp_path) == (tmp_path.resolve(),)


def test_discover_skips_submodule_escaping_root(tmp_path: Path) -> None:
    # A crafted `path = ../outside` resolves above the session root — the
    # gate must not evaluate drift on a directory outside the project.
    inner = tmp_path / "repo"
    inner.mkdir()
    _declare_submodule(inner, "x", "../outside")
    _mk_index(tmp_path / "outside")   # give it an index so absence isn't the cause
    assert rg.discover_context_roots(inner) == (inner.resolve(),)


# ----- multi-root decide_block ----------------------------------------------


def _significant():
    return SessionSignal(output_tokens=50_000, subagent_file_count=0, main_turns=3)


def test_blocks_when_only_submodule_index_is_stale(monkeypatch, tmp_path: Path):
    be = _declare_submodule(tmp_path, "backend", "backend")
    _mk_index(be)
    stale = DriftReport(rows=(DriftRow(rel_path="api.py", feature_id="orders"),))

    def fake_drift(r: Path) -> DriftReport:
        return stale if r.resolve() == be.resolve() else DriftReport(rows=())

    monkeypatch.setattr(rg, "compute_drift", fake_drift)
    monkeypatch.setattr(rg, "read_session_signal", lambda p: _significant())
    out = rg.decide_block(
        root=tmp_path, main_transcript=_transcript(tmp_path), stop_hook_active=False
    )
    assert out is not None
    reason = json.loads(out)["reason"]
    assert "orders" in reason
    assert "backend" in reason
    assert "reconcile-stamp --root backend" in reason


def test_blocks_when_both_root_and_submodule_stale(monkeypatch, tmp_path: Path):
    be = _declare_submodule(tmp_path, "backend", "backend")
    _mk_index(be)
    _mk_index(tmp_path)

    def fake_drift(r: Path) -> DriftReport:
        if r.resolve() == be.resolve():
            return DriftReport(rows=(DriftRow(rel_path="api.py", feature_id="orders"),))
        return DriftReport(rows=(DriftRow(rel_path="app.py", feature_id="shell"),))

    monkeypatch.setattr(rg, "compute_drift", fake_drift)
    monkeypatch.setattr(rg, "read_session_signal", lambda p: _significant())
    out = rg.decide_block(
        root=tmp_path, main_transcript=_transcript(tmp_path), stop_hook_active=False
    )
    assert out is not None
    reason = json.loads(out)["reason"]
    # Multi-section message: both indexes named, submodule stamp scoped.
    assert "shell" in reason and "orders" in reason
    assert "(session root)" in reason
    assert "reconcile-stamp --root backend" in reason


def test_submodule_opt_out_respected(monkeypatch, tmp_path: Path):
    be = _declare_submodule(tmp_path, "backend", "backend")
    _mk_index(be)
    _write_cfg(be, {"auto_council": False})

    def fake_drift(r: Path) -> DriftReport:
        # Only the (opted-out) submodule drifts; the root is clean.
        return (
            DriftReport(rows=(DriftRow(rel_path="a.py", feature_id="x"),))
            if r.resolve() == be.resolve()
            else DriftReport(rows=())
        )

    monkeypatch.setattr(rg, "compute_drift", fake_drift)
    monkeypatch.setattr(rg, "read_session_signal", lambda p: _significant())
    out = rg.decide_block(
        root=tmp_path, main_transcript=_transcript(tmp_path), stop_hook_active=False
    )
    assert out is None


def test_root_master_opt_out_silences_submodules(monkeypatch, tmp_path: Path):
    _write_cfg(tmp_path, {"auto_council": False})
    be = _declare_submodule(tmp_path, "backend", "backend")
    _mk_index(be)
    monkeypatch.setattr(
        rg,
        "compute_drift",
        lambda r: DriftReport(rows=(DriftRow(rel_path="a.py", feature_id="x"),)),
    )
    monkeypatch.setattr(rg, "read_session_signal", lambda p: _significant())
    out = rg.decide_block(
        root=tmp_path, main_transcript=_transcript(tmp_path), stop_hook_active=False
    )
    assert out is None


# ----- render_multi_block ---------------------------------------------------


def test_render_multi_block_scopes_each_root() -> None:
    base = Path("/repo")
    stale = [
        (
            base,
            DriftReport(rows=(DriftRow(rel_path="a.py", feature_id="core"),)),
        ),
        (
            base / "backend",
            DriftReport(
                rows=(DriftRow(rel_path="b.py", feature_id="orders"),),
                awaiting_enrichment=("search",),
            ),
        ),
    ]
    obj = json.loads(rg.render_multi_block(stale, base=base))
    assert obj["decision"] == "block"
    reason = obj["reason"]
    assert "core" in reason and "orders" in reason
    assert "backend" in reason
    assert "search" in reason
    # base stamp stays bare; submodule stamp is --root scoped.
    assert "reconcile-stamp --root backend" in reason
    assert "auto_council" in reason


def test_render_multi_block_reports_unassigned_new_files() -> None:
    base = Path("/repo")
    stale = [
        (
            base / "frontend",
            DriftReport(rows=(), unassigned_new_files=("src/new.ts",)),
        ),
    ]
    reason = json.loads(rg.render_multi_block(stale, base=base))["reason"]
    assert "new unplaced files src/new.ts" in reason
    assert "frontend" in reason


def test_render_multi_block_root_outside_base_uses_absolute_path() -> None:
    # A ctx_root that isn't under base falls back to its absolute path label.
    base = Path("/repo")
    stale = [
        (
            Path("/other/place"),
            DriftReport(rows=(DriftRow(rel_path="a.py", feature_id="x"),)),
        ),
    ]
    reason = json.loads(rg.render_multi_block(stale, base=base))["reason"]
    assert "/other/place" in reason
    assert "reconcile-stamp --root /other/place" in reason
