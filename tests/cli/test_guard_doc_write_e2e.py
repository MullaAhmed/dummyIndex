"""Tests for the PreToolUse Write-guard (`guard-doc-write`).

Two layers:

- ``decision.py`` unit tests (`@pytest.mark.unit`) — the pure builder maps a
  :class:`DocClassification` to the deny payload (interpolated home/slug/file)
  or to ``{}`` (allow).
- e2e subprocess + in-process tests (`@pytest.mark.integration`) — the
  ``guard_doc_write.run`` entrypoint across the real process + stdin boundary.

The ``guard-doc-write`` verb is NOT registered in the ``context`` dispatcher yet
(a later wave), so the subprocess invokes ``run`` directly via ``python -c``
rather than ``python -m dummyindex context guard-doc-write`` — still exercising
the process + stdin seam the way ``test_reconcile_gate_e2e`` does.

The guard's whole contract is fail-open: it ALWAYS exits 0 (never ``exit 2``),
speaking only through a JSON ``deny`` payload on stdout.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from dummyindex.context.domains.config import default_config, write_config
from dummyindex.context.domains.docguard.decision import decide
from dummyindex.context.domains.docguard.enums import DocKind, DocRole
from dummyindex.context.domains.docguard.models import DocClassification

# ----- helpers --------------------------------------------------------------

_RUN_CODE = (
    "import sys; from dummyindex.cli.guard_doc_write import run; "
    "sys.exit(run(sys.argv[1:]))"
)


def _invoke(
    repo: Path, *, stdin: str, extra_args: tuple[str, ...] = ()
) -> subprocess.CompletedProcess[str]:
    """Drive ``guard_doc_write.run`` through a real subprocess + stdin."""
    return subprocess.run(
        [sys.executable, "-c", _RUN_CODE, "--root", str(repo), *extra_args],
        input=stdin,
        capture_output=True,
        text=True,
    )


def _write_payload(tool_name: str, file_path: str | None) -> str:
    tool_input: dict[str, object] = {"content": "# doc\n"}
    if file_path is not None:
        tool_input["file_path"] = file_path
    return json.dumps({"tool_name": tool_name, "tool_input": tool_input})


def _write_config(repo: Path, **overrides: object) -> None:
    cfg = replace(default_config(), **overrides)
    write_config(repo / ".context", cfg)


def _planning_classification(
    *, role: DocRole = DocRole.SPEC, **overrides: object
) -> DocClassification:
    base: dict[str, object] = dict(
        is_planning_doc=True,
        kind=DocKind.PROPOSAL,
        in_managed_location=False,
        suggested_slug="x",
        suggested_home=".context/proposals/x",
        role=role,
        pairing_stem="x",
        rel_path="docs/specs/x-design.md",
    )
    base.update(overrides)
    return DocClassification(**base)  # type: ignore[arg-type]


# ----- decision.py unit tests -----------------------------------------------


@pytest.mark.unit
def test_decision_denies_stray_with_interpolated_home() -> None:
    payload = decide(_planning_classification(role=DocRole.SPEC))
    out = payload["hookSpecificOutput"]
    assert out["hookEventName"] == "PreToolUse"
    assert out["permissionDecision"] == "deny"
    reason = out["permissionDecisionReason"]
    # Home, slug, file, and the original path are all interpolated.
    assert "docs/specs/x-design.md" in reason
    assert ".context/proposals/x/spec.md" in reason
    assert reason.endswith("instead of docs/.")


@pytest.mark.unit
def test_decision_uses_plan_md_for_plan_role() -> None:
    payload = decide(
        _planning_classification(role=DocRole.PLAN, rel_path="docs/plans/x.md")
    )
    reason = payload["hookSpecificOutput"]["permissionDecisionReason"]
    assert ".context/proposals/x/plan.md" in reason
    assert "spec.md" not in reason


@pytest.mark.unit
def test_decision_interpolates_audit_home() -> None:
    payload = decide(
        _planning_classification(
            kind=DocKind.AUDIT,
            suggested_home=".context/audits/x",
            role=DocRole.PLAN,
            rel_path="docs/internal/audits/x.md",
        )
    )
    reason = payload["hookSpecificOutput"]["permissionDecisionReason"]
    assert ".context/audits/x/plan.md" in reason


@pytest.mark.unit
def test_decision_allows_non_planning_doc() -> None:
    dc = DocClassification(
        is_planning_doc=False,
        kind=DocKind.NONE,
        in_managed_location=False,
        rel_path="docs/guide/x.md",
    )
    assert decide(dc) == {}


@pytest.mark.unit
def test_decision_allows_managed_location() -> None:
    # Even a planning doc already in a managed location is allowed.
    dc = _planning_classification(
        in_managed_location=True, rel_path=".context/proposals/foo/spec.md"
    )
    assert decide(dc) == {}


@pytest.mark.unit
def test_decision_allows_unplaceable_stray() -> None:
    # A planning doc with no slug-able home (suggested_home=None) fails open
    # rather than emitting a nonsensical "None/spec.md" deny.
    dc = _planning_classification(suggested_slug=None, suggested_home=None)
    assert decide(dc) == {}


# ----- e2e: deny / allow over the real subprocess ---------------------------


@pytest.mark.integration
def test_write_to_stray_spec_denies(tmp_path: Path) -> None:
    repo = tmp_path.resolve()
    stray = str(repo / "docs" / "specs" / "x-design.md")
    out = _invoke(repo, stdin=_write_payload("Write", stray))
    assert out.returncode == 0, out.stderr
    payload = json.loads(out.stdout)
    deny = payload["hookSpecificOutput"]
    assert deny["permissionDecision"] == "deny"
    assert ".context/proposals/x/spec.md" in deny["permissionDecisionReason"]
    # The exact compact shape the spec pins.
    assert '"permissionDecision":"deny"' in out.stdout


@pytest.mark.integration
def test_write_to_managed_location_allows(tmp_path: Path) -> None:
    repo = tmp_path.resolve()
    managed = str(repo / ".context" / "proposals" / "foo" / "spec.md")
    out = _invoke(repo, stdin=_write_payload("Write", managed))
    assert out.returncode == 0, out.stderr
    assert out.stdout == ""


@pytest.mark.integration
def test_write_to_user_doc_allows(tmp_path: Path) -> None:
    repo = tmp_path.resolve()
    guide = str(repo / "docs" / "guide" / "x.md")
    out = _invoke(repo, stdin=_write_payload("Write", guide))
    assert out.returncode == 0, out.stderr
    assert out.stdout == ""


# ----- e2e: fail-open everywhere --------------------------------------------


@pytest.mark.integration
def test_malformed_stdin_allows(tmp_path: Path) -> None:
    out = _invoke(tmp_path.resolve(), stdin="{ this is not json")
    assert out.returncode == 0, out.stderr
    assert out.stdout == ""


@pytest.mark.integration
def test_empty_stdin_allows(tmp_path: Path) -> None:
    out = _invoke(tmp_path.resolve(), stdin="")
    assert out.returncode == 0, out.stderr
    assert out.stdout == ""


@pytest.mark.integration
@pytest.mark.parametrize("tool_name", ["Edit", "MultiEdit", "Read", "Bash"])
def test_non_write_tool_allows(tmp_path: Path, tool_name: str) -> None:
    repo = tmp_path.resolve()
    stray = str(repo / "docs" / "specs" / "x-design.md")
    out = _invoke(repo, stdin=_write_payload(tool_name, stray))
    assert out.returncode == 0, out.stderr
    assert out.stdout == ""


@pytest.mark.integration
def test_missing_file_path_allows(tmp_path: Path) -> None:
    repo = tmp_path.resolve()
    out = _invoke(repo, stdin=_write_payload("Write", None))
    assert out.returncode == 0, out.stderr
    assert out.stdout == ""


@pytest.mark.integration
def test_file_path_outside_repo_allows(tmp_path: Path) -> None:
    repo = tmp_path.resolve()
    # An absolute path that cannot be made relative to repo → DocPathError →
    # fail open.
    outside = "/somewhere/else/docs/specs/x-design.md"
    out = _invoke(repo, stdin=_write_payload("Write", outside))
    assert out.returncode == 0, out.stderr
    assert out.stdout == ""


@pytest.mark.integration
def test_unknown_arg_does_not_return_two(tmp_path: Path) -> None:
    # A leftover/unknown arg must NOT trigger reconcile_gate's `return 2`.
    out = _invoke(tmp_path.resolve(), stdin="", extra_args=("--bogus",))
    assert out.returncode == 0, out.stderr
    assert out.stdout == ""


@pytest.mark.integration
@pytest.mark.parametrize(
    "stdin",
    [
        "",
        "{ malformed",
        json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "x"}}),
        json.dumps({"tool_name": "Write", "tool_input": {}}),
        json.dumps(
            {"tool_name": "Write", "tool_input": {"file_path": "docs/specs/x.md"}}
        ),
    ],
)
def test_never_returns_two(tmp_path: Path, stdin: str) -> None:
    out = _invoke(tmp_path.resolve(), stdin=stdin)
    assert out.returncode == 0
    assert out.returncode != 2


# ----- config gate ----------------------------------------------------------


@pytest.mark.integration
def test_config_disabled_allows_stray(tmp_path: Path) -> None:
    repo = tmp_path.resolve()
    _write_config(repo, doc_guard_enabled=False)
    stray = str(repo / "docs" / "specs" / "x-design.md")
    out = _invoke(repo, stdin=_write_payload("Write", stray))
    assert out.returncode == 0, out.stderr
    assert out.stdout == ""


@pytest.mark.integration
def test_config_absent_engages_guard(tmp_path: Path) -> None:
    # No config at all → default-on → the stray is denied.
    repo = tmp_path.resolve()
    assert not (repo / ".context" / "config.json").exists()
    stray = str(repo / "docs" / "specs" / "x-design.md")
    out = _invoke(repo, stdin=_write_payload("Write", stray))
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.integration
def test_config_malformed_engages_guard(tmp_path: Path) -> None:
    # Malformed config → the tolerant accessor returns its (True, ()) default,
    # so the guard stays engaged (default-on) and denies the stray.
    repo = tmp_path.resolve()
    (repo / ".context").mkdir(parents=True)
    (repo / ".context" / "config.json").write_text(
        "{ not: valid json", encoding="utf-8"
    )
    stray = str(repo / "docs" / "specs" / "x-design.md")
    out = _invoke(repo, stdin=_write_payload("Write", stray))
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.integration
def test_allowlist_exempts_published_path(tmp_path: Path) -> None:
    repo = tmp_path.resolve()
    _write_config(repo, doc_guard_allow=("docs/specs/**",))
    stray = str(repo / "docs" / "specs" / "x-design.md")
    out = _invoke(repo, stdin=_write_payload("Write", stray))
    assert out.returncode == 0, out.stderr
    assert out.stdout == ""  # matched the allow glob → allowed


# ----- in-process: prove fail-open + no-subprocess on the guard path ---------


def _feed_stdin(monkeypatch: pytest.MonkeyPatch, payload: str) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))


@pytest.mark.integration
def test_classify_raises_fails_open_in_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A classifier that raises must be swallowed → exit 0, no output. (Can't
    # monkeypatch across a subprocess, so this case runs in-process.)
    import dummyindex.cli.guard_doc_write as guard

    def _boom(*_a: object, **_k: object) -> object:
        raise RuntimeError("classifier blew up")

    monkeypatch.setattr(
        "dummyindex.context.domains.docguard.classify.classify_doc_path", _boom
    )
    repo = tmp_path.resolve()
    stray = str(repo / "docs" / "specs" / "x-design.md")
    _feed_stdin(monkeypatch, _write_payload("Write", stray))

    rc = guard.run(["--root", str(repo)])

    assert rc == 0
    assert capsys.readouterr().out == ""


@pytest.mark.integration
def test_no_subprocess_on_guard_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The guard path must invoke NO subprocess: monkeypatch subprocess.run to
    # raise, then prove the guard still classifies + denies a stray.
    import subprocess as _subprocess

    import dummyindex.cli.guard_doc_write as guard

    # Warm the lazy imports so the monkeypatch can't trip an import-time call.
    import dummyindex.context.domains.config  # noqa: F401
    import dummyindex.context.domains.docguard.classify  # noqa: F401
    import dummyindex.context.domains.docguard.decision  # noqa: F401

    def _no_subprocess(*_a: object, **_k: object) -> object:
        raise AssertionError("guard path must not invoke subprocess.run")

    monkeypatch.setattr(_subprocess, "run", _no_subprocess)
    repo = tmp_path.resolve()
    stray = str(repo / "docs" / "specs" / "x-design.md")
    _feed_stdin(monkeypatch, _write_payload("Write", stray))

    rc = guard.run(["--root", str(repo)])

    assert rc == 0
    out = capsys.readouterr().out
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"
