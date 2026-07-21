"""Tests for the Stop-hook reconcile gate decision logic."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from dummyindex.context import reconcile_gate as rg
from dummyindex.context.domains.memory.transcript import SessionSignal
from dummyindex.context.drift import DriftReport, DriftRow
from dummyindex.context.reconcile_gate import (
    auto_council_enabled,
    render_block,
)


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(path), check=True, capture_output=True, text=True
    ).stdout


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
    # The refresh must land as its own tracked commit (session-end update wiring).
    assert "git add .context" in reason
    assert "docs(context)" in reason
    assert "auto_council" in reason


# ----- decide_block ---------------------------------------------------------


@pytest.fixture
def patched(monkeypatch, tmp_path):
    state = {
        "enabled": True,
        "report": DriftReport(
            rows=(DriftRow(rel_path="a.py", feature_id="auth"),),
            unassigned_new_files=("new/x.py",),
        ),
        "signal": SessionSignal(
            output_tokens=50_000,
            subagent_file_count=0,
            main_turns=3,
            edited_paths=(str(tmp_path / "app" / "x.py"),),
        ),
    }
    monkeypatch.setattr(rg, "auto_council_enabled", lambda root: state["enabled"])
    monkeypatch.setattr(rg, "compute_drift", lambda root: state["report"])
    monkeypatch.setattr(rg, "read_session_signal", lambda p: state["signal"])
    # Default: the gate sees a present anchor (so mtime-only never blocks on its
    # own); tests that need the no-anchor branch override this.
    monkeypatch.setattr(rg, "_has_live_anchor", lambda root: True)
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


# ----- session attribution --------------------------------------------------


def test_silent_when_session_edited_nothing_outside_context(patched):
    """A planning-only / git-only session (no source edits outside
    .context/.claude) must not be trapped, even with inherited drift."""
    state, root = patched
    state["signal"] = SessionSignal(
        output_tokens=50_000,
        subagent_file_count=0,
        main_turns=3,
        edited_paths=(
            str(root / ".context" / "features" / "x" / "plan.md"),
            str(root / ".claude" / "settings.json"),
        ),
    )
    out = rg.decide_block(
        root=root, main_transcript=_transcript(root), stop_hook_active=False
    )
    assert out is None


def test_blocks_when_session_edited_real_source(patched):
    state, root = patched
    state["signal"] = SessionSignal(
        output_tokens=50_000,
        subagent_file_count=0,
        main_turns=3,
        edited_paths=(str(root / "app" / "x.py"),),
    )
    out = rg.decide_block(
        root=root, main_transcript=_transcript(root), stop_hook_active=False
    )
    assert out is not None


# ----- block-once-per-session memo ------------------------------------------


def test_blocks_once_then_allows_same_session(patched):
    state, root = patched
    first = rg.decide_block(
        root=root,
        main_transcript=_transcript(root),
        stop_hook_active=False,
        session_id="sess-1",
    )
    assert first is not None
    # Memo persisted under the gitignored cache dir.
    assert (root / ".context" / "cache" / "reconcile-gate-state.json").exists()
    # A later stop in the SAME session, even with stop_hook_active=false, is
    # silent — the gate is a one-time prompt, not a trap.
    second = rg.decide_block(
        root=root,
        main_transcript=_transcript(root),
        stop_hook_active=False,
        session_id="sess-1",
    )
    assert second is None


def test_different_session_blocks_again(patched):
    state, root = patched
    rg.decide_block(
        root=root,
        main_transcript=_transcript(root),
        stop_hook_active=False,
        session_id="sess-1",
    )
    out = rg.decide_block(
        root=root,
        main_transcript=_transcript(root),
        stop_hook_active=False,
        session_id="sess-2",
    )
    assert out is not None


# ----- mtime-only drift downgrade -------------------------------------------


def test_silent_when_anchor_present_and_no_commit_anchored_signal(patched, monkeypatch):
    """With a live anchor and a clean commit-anchored report (mtime rows only,
    NO ``drifted_features`` / unassigned / awaiting), the gate stays silent —
    mtime alone is a SessionStart advisory, not a Stop block.

    This REPLACES the former ``test_silent_when_only_mtime_drift_and_anchor_present``,
    which asserted silence for a report that effectively stood in for a committed
    owned-file modification — locking in the F6 bug. The remaining correct
    behaviour is preserved here: a genuinely clean commit-anchored view (no
    drifted_features) on an anchored repo does not block on bare mtime rows.
    """
    state, root = patched
    state["report"] = DriftReport(
        rows=(DriftRow(rel_path="a.py", feature_id="auth"),),
        # explicit: no commit-anchored signal — the only thing that should keep
        # an anchored repo blocking-relevant.
        drifted_features=(),
    )
    out = rg.decide_block(
        root=root, main_transcript=_transcript(root), stop_hook_active=False
    )
    assert out is None


def test_mtime_drift_blocks_when_no_anchor(patched, monkeypatch):
    """Anchor-less repos still block on mtime drift — it's the only signal."""
    state, root = patched
    state["report"] = DriftReport(rows=(DriftRow(rel_path="a.py", feature_id="auth"),))
    monkeypatch.setattr(rg, "_has_live_anchor", lambda r: False)
    out = rg.decide_block(
        root=root, main_transcript=_transcript(root), stop_hook_active=False
    )
    assert out is not None


# ----- render_block conditional directives ----------------------------------


def test_render_block_omits_recouncil_when_no_features() -> None:
    report = DriftReport(rows=(), unassigned_new_files=("new/x.py",))
    reason = json.loads(rg.render_block(report))["reason"]
    assert "re-run its council enrichment" not in reason
    # Placement-only directive present instead.
    assert "place" in reason.lower()
    assert "new/x.py" in reason


def test_render_block_includes_recouncil_when_features() -> None:
    report = DriftReport(rows=(DriftRow(rel_path="a.py", feature_id="auth"),))
    reason = json.loads(rg.render_block(report))["reason"]
    assert "recouncil" in reason
    assert "auth" in reason


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
    _mk_index(tmp_path / "outside")  # give it an index so absence isn't the cause
    assert rg.discover_context_roots(inner) == (inner.resolve(),)


# ----- multi-root decide_block ----------------------------------------------


def _significant(root: Path | None = None):
    # A real source edit so session-attribution lets the gate fire; the path
    # need only resolve under (or outside) the project — here we pass an
    # absolute path under the test root so attribution counts it.
    edited = (str((root or Path("/repo")) / "app" / "edited.py"),)
    return SessionSignal(
        output_tokens=50_000,
        subagent_file_count=0,
        main_turns=3,
        edited_paths=edited,
    )


def test_blocks_when_only_submodule_index_is_stale(monkeypatch, tmp_path: Path):
    be = _declare_submodule(tmp_path, "backend", "backend")
    _mk_index(be)
    stale = DriftReport(rows=(DriftRow(rel_path="api.py", feature_id="orders"),))

    def fake_drift(r: Path) -> DriftReport:
        return stale if r.resolve() == be.resolve() else DriftReport(rows=())

    monkeypatch.setattr(rg, "compute_drift", fake_drift)
    monkeypatch.setattr(rg, "read_session_signal", lambda p: _significant(tmp_path))
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
    monkeypatch.setattr(rg, "read_session_signal", lambda p: _significant(tmp_path))
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
    monkeypatch.setattr(rg, "read_session_signal", lambda p: _significant(tmp_path))
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
    monkeypatch.setattr(rg, "read_session_signal", lambda p: _significant(tmp_path))
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
    # Each refreshed index lands as its own dedicated, tracked commit.
    assert "docs(context)" in reason
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


@pytest.mark.unit
def test_gate_non_source_check_is_the_shared_predicate() -> None:
    """F11: the gate's non-source check IS the single shared predicate exported
    from ``build/reconcile.py`` — not a locally-duplicated prefix set.

    The old ``_NON_SOURCE_PREFIXES`` duplication (and the sync-enforcing test
    that policed it) is gone; the gate now imports ``is_non_source_path``
    directly. We assert identity (same function object) AND behavioural parity
    across the index, the tool footprint, and a real source path.
    """
    from dummyindex.context.build import reconcile as rc

    # Identity: the gate uses the canonical predicate, not a copy.
    assert rg.is_non_source_path is rc.is_non_source_path
    # The duplicated prefix set is gone.
    assert not hasattr(rg, "_NON_SOURCE_PREFIXES")

    # Behavioural parity across the categories the old set covered.
    for non_source in (
        ".context",
        ".context/meta.json",
        ".claude",
        ".claude/settings.json",
        ".agents",
        ".agents/skills/dummyindex/SKILL.md",
        "packages/api/.agents/skills/local/SKILL.md",
        ".codex",
        ".codex/agents/reviewer.toml",
        "packages/api/.codex/config.toml",
        "AGENTS.md",
        "AGENTS.override.md",
        "packages/api/AGENTS.md",
        "docs/AGENTS.override.md",
        ".claude-design",
        ".claude-design/x.json",
    ):
        assert rg.is_non_source_path(non_source) is True
        assert rc.is_non_source_path(non_source) is True
    for source in ("app/service.py", "src/main.ts", "README.md"):
        assert rg.is_non_source_path(source) is False
        assert rc.is_non_source_path(source) is False


@pytest.mark.unit
def test_gate_ignores_configured_codex_fallback_guidance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dummyindex.context.build import reconcile as rc

    codex_home = tmp_path / "user-codex-home"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(
        f'[projects.{json.dumps(str(tmp_path.resolve()))}]\ntrust_level = "trusted"\n',
        encoding="utf-8",
    )
    project_codex = tmp_path / ".codex"
    project_codex.mkdir()
    (project_codex / "config.toml").write_text(
        'project_doc_fallback_filenames = ["TEAM_GUIDE.md"]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    assert rg.is_non_source_path("TEAM_GUIDE.md", project_root=tmp_path) is True
    assert (
        rc.is_non_source_path(
            "packages/api/TEAM_GUIDE.md",
            project_root=tmp_path,
        )
        is True
    )
    assert (
        rg._session_drifted_source((str(tmp_path / "TEAM_GUIDE.md"),), tmp_path)
        is False
    )


@pytest.mark.unit
def test_nested_codex_fallback_matches_path_suffix_not_basename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dummyindex.context.build import reconcile as rc

    codex_home = tmp_path / "user-codex-home"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(
        f'[projects.{json.dumps(str(tmp_path.resolve()))}]\ntrust_level = "trusted"\n',
        encoding="utf-8",
    )
    project_codex = tmp_path / ".codex"
    project_codex.mkdir()
    (project_codex / "config.toml").write_text(
        'project_doc_fallback_filenames = ["guidance/TEAM_GUIDE.md"]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    for guidance in (
        "guidance/TEAM_GUIDE.md",
        "packages/api/guidance/TEAM_GUIDE.md",
    ):
        assert rg.is_non_source_path(guidance, project_root=tmp_path) is True
        assert rc.is_non_source_path(guidance, project_root=tmp_path) is True
        assert (
            rg._session_drifted_source((str(tmp_path / guidance),), tmp_path) is False
        )

    for source in ("TEAM_GUIDE.md", "docs/TEAM_GUIDE.md"):
        assert rg.is_non_source_path(source, project_root=tmp_path) is False
        assert rc.is_non_source_path(source, project_root=tmp_path) is False
        assert rg._session_drifted_source((str(tmp_path / source),), tmp_path) is True


@pytest.mark.unit
def test_gate_ignores_claude_design_only_session(tmp_path: Path) -> None:
    """A session that edited only .claude-design/ files did not drift source."""
    base = tmp_path
    assert (
        rg._session_drifted_source((str(base / ".claude-design/x.json"),), base)
        is False
    )


# ----- T-C: genuinely stamped, anchored repo (F6, BLOCK-grade) --------------


def _stamped_anchored_repo(root: Path) -> str:
    """Stand up a REAL stamped, anchored ``.context/`` over a git repo.

    Commits a source file owned by feature ``auth``, writes a real ``meta.json``
    (via ``new_meta``/``write_meta``), then calls the REAL ``stamp_reconciled``
    (the exact function the ``reconcile-stamp`` CLI verb wraps) to advance the
    anchor to HEAD. No monkeypatch of ``_has_live_anchor`` — the anchor is a
    genuine commit recorded in ``meta.indexed_commit``. Returns the stamped sha.
    """
    from dummyindex.context.build.meta import new_meta, write_meta
    from dummyindex.context.build.reconcile import stamp_reconciled

    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t.t")
    _git(root, "config", "user.name", "t")
    (root / "auth.py").write_text("def login(): return 1\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "init")

    context_dir = root / ".context"
    feat = context_dir / "features" / "auth"
    feat.mkdir(parents=True)
    (feat / "feature.json").write_text(
        json.dumps({"feature_id": "auth", "files": ["auth.py"]}), encoding="utf-8"
    )
    (feat / "spec.md").write_text("# auth\n", encoding="utf-8")
    write_meta(context_dir / "meta.json", new_meta(root, "0.28.0"))

    result = stamp_reconciled(context_dir, root)
    assert result.stamped_commit is not None and not result.refused
    return result.stamped_commit


@pytest.mark.integration
def test_block_for_committed_owned_file_on_real_anchor(tmp_path: Path) -> None:
    """F6 — the BLOCK-grade red-before-green test.

    On a GENUINELY stamped, anchored repo, a session that modified + committed a
    file owned by an existing feature must produce a Stop block whose ``reason``
    names that feature.

    This is the F6 capture: pre-fix, ``compute_drift`` dropped
    ``reconcile.drifted_features`` (drift.py:171-175) so it never reached the
    gate, AND an anchored repo suppresses the mtime ``rows`` branch
    (``_gate_relevant``) — so ``decide_block`` returned ``None`` (NO block) for
    exactly this scenario. The fix forwards ``drifted_features`` and makes
    ``_gate_relevant`` count it independent of the anchor. Verified against the
    pre-fix shape in ``test_drift.py`` (replace(report, drifted_features=()) →
    _gate_relevant False) — i.e. this test FAILS on the pre-fix code.

    NO monkeypatch of ``_has_live_anchor``: we assert the real anchor is reached.
    """
    stamped = _stamped_anchored_repo(tmp_path)

    # The anchor is genuinely live — reached naturally, no monkeypatch.
    assert rg._has_live_anchor(tmp_path) is True

    # A committed modification of the owned file → drifted_features=("auth",).
    (tmp_path / "auth.py").write_text("def login(): return 2\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "change auth")

    # A substantial session that actually edited the owned source file. The
    # transcript MUST live OUTSIDE the repo tree — an untracked file inside the
    # repo would surface as `unassigned_new_files` (an anchor-independent signal)
    # and let the pre-fix code block for the wrong reason, masking the F6 capture.
    transcript = tmp_path.parent / f"{tmp_path.name}-session.jsonl"
    transcript.write_text(
        json.dumps(
            {"type": "assistant", "message": {"usage": {"output_tokens": 100_000}}}
        )
        + "\n"
        + json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Edit",
                            "input": {"file_path": str(tmp_path / "auth.py")},
                        }
                    ]
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    out = rg.decide_block(
        root=tmp_path,
        main_transcript=transcript,
        stop_hook_active=False,
        session_id="sess-tc",
    )
    assert out is not None, "F6: anchored committed owned-file edit must block"
    obj = json.loads(out)
    assert obj["decision"] == "block"
    assert "auth" in obj["reason"]
    # Sanity: the stamped anchor we built is the one driving the diff.
    assert len(stamped) >= 7


# ----- F9: session-id present but transcript unreadable ----------------------


@pytest.mark.integration
def test_advisory_block_when_session_id_but_transcript_unreadable(patched):
    """F9: a session id IS present but its transcript is missing/unreadable on a
    gate-relevant index → conservative advisory block (not a hard-allow)."""
    state, root = patched
    state["report"] = DriftReport(
        rows=(),
        unassigned_new_files=("new/x.py",),  # commit-anchored, always relevant
    )
    missing = root / "does-not-exist.jsonl"
    out = rg.decide_block(
        root=root,
        main_transcript=missing,
        stop_hook_active=False,
        session_id="sess-unreadable",
    )
    assert out is not None
    obj = json.loads(out)
    assert obj["decision"] == "block"
    assert "advisory" in obj["reason"].lower()


@pytest.mark.integration
def test_headless_no_session_id_hard_allows(patched):
    """F9 scope: NO session id (headless / CI / e2e subprocess) → hard-allow,
    even on a gate-relevant index with no transcript."""
    state, root = patched
    state["report"] = DriftReport(
        rows=(),
        unassigned_new_files=("new/x.py",),
    )
    out = rg.decide_block(
        root=root,
        main_transcript=None,
        stop_hook_active=False,
        session_id="",  # headless
    )
    assert out is None


# ----- F10: subagent edit count drives source-drift -------------------------


def _write_subagent_jsonl(main_transcript: Path, name: str, *blocks: dict) -> None:
    """Write a real ``<transcript>/subagents/<name>.jsonl`` with one assistant
    envelope carrying ``blocks`` as its content (mirrors the real envelope)."""
    sub_dir = main_transcript.with_suffix("") / "subagents"
    sub_dir.mkdir(parents=True, exist_ok=True)
    (sub_dir / name).write_text(
        json.dumps({"type": "assistant", "message": {"content": list(blocks)}}) + "\n",
        encoding="utf-8",
    )


@pytest.mark.unit
def test_session_drifted_false_for_readonly_fanout(tmp_path: Path) -> None:
    """F10: a read-only subagent fan-out (subagent files exist, but ZERO edits)
    does not by itself make ``_session_drifted_source`` return True."""
    base = tmp_path
    assert rg._session_drifted_source((), base, subagent_edit_count=0) is False


@pytest.mark.unit
def test_session_drifted_true_for_build_style_subagent_edit(tmp_path: Path) -> None:
    """F10: a build-style run whose edits happen INSIDE a subagent
    (subagent_edit_count > 0) makes ``_session_drifted_source`` return True,
    even when the main thread edited nothing — build-detection preserved."""
    base = tmp_path
    assert rg._session_drifted_source((), base, subagent_edit_count=1) is True


@pytest.mark.unit
def test_subagent_edit_count_parses_real_envelope(tmp_path: Path) -> None:
    """F10: the real ``subagents/agent-*.jsonl`` envelope is parsed for Edit/Write
    tool-uses by ``read_session_signal`` — a read-only fan-out yields 0, an edit
    yields >0. Verifies the envelope shape the gate keys on."""
    from dummyindex.context.domains.memory.transcript import read_session_signal

    main = tmp_path / "t.jsonl"
    main.write_text(
        json.dumps({"type": "assistant", "message": {"usage": {"output_tokens": 100}}})
        + "\n",
        encoding="utf-8",
    )
    # Read-only subagent: a Read/Grep tool-use, no Edit/Write.
    _write_subagent_jsonl(
        main,
        "agent-readonly.jsonl",
        {"type": "tool_use", "name": "Read", "input": {"file_path": "x.py"}},
    )
    assert read_session_signal(main).subagent_edit_count == 0

    # Build-style subagent: an Edit tool-use.
    _write_subagent_jsonl(
        main,
        "agent-build.jsonl",
        {
            "type": "tool_use",
            "name": "Edit",
            "input": {"file_path": str(tmp_path / "app" / "x.py")},
        },
    )
    assert read_session_signal(main).subagent_edit_count == 1


@pytest.mark.unit
def test_decide_block_for_readonly_subagents_plus_main_thread_edit(
    patched, monkeypatch
):
    """F10: read-only subagents (zero subagent edits) PLUS a real main-thread
    source edit still blocks — the main-thread path-check carries it."""
    state, root = patched
    state["signal"] = SessionSignal(
        output_tokens=50_000,
        subagent_file_count=2,  # fan-out happened
        main_turns=3,
        edited_paths=(str(root / "app" / "x.py"),),  # real main-thread source edit
        subagent_edit_count=0,  # but the subagents only read
    )
    out = rg.decide_block(
        root=root, main_transcript=_transcript(root), stop_hook_active=False
    )
    assert out is not None
    assert json.loads(out)["decision"] == "block"
