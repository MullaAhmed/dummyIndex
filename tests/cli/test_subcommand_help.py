"""Every context subcommand answers -h / --help (read-only, exit 0).

The CLI is a hand-rolled dispatcher, not argparse: before this guard, a
``--help`` token after a subcommand fell through to the handler's
leftover-args check and exited 2 (or, for ``hooks``, was misread as a verb).
Worse, the probe that followed a failed ``--help`` — running the bare verb —
could MUTATE the repo (``equip``). These tests pin the contract:

- ``dispatch([sub, '--help'])`` and ``dispatch([sub, '-h'])`` exit 0,
- print a non-empty usage block naming the subcommand,
- and write NOTHING to disk (run in a throwaway cwd).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.context.enums import ContextSubcommand


def _snapshot(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*")}


@pytest.mark.unit
@pytest.mark.parametrize("sub", list(ContextSubcommand), ids=lambda s: s.value)
@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_every_subcommand_answers_help(
    sub: ContextSubcommand,
    flag: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dummyindex.cli import dispatch

    monkeypatch.chdir(tmp_path)
    before = _snapshot(tmp_path)

    code = dispatch([sub.value, flag])

    out = capsys.readouterr().out
    assert code == 0, f"`context {sub.value} {flag}` should exit 0, got {code}"
    assert out.strip(), f"`context {sub.value} {flag}` printed nothing"
    assert sub.value in out, (
        f"`context {sub.value} {flag}` usage does not name the subcommand"
    )
    after = _snapshot(tmp_path)
    assert before == after, (
        f"`context {sub.value} {flag}` mutated the cwd: {sorted(after - before)}"
    )


@pytest.mark.unit
def test_help_token_after_verbed_subcommand(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A nested verb's --help still resolves to the parent subcommand usage."""
    from dummyindex.cli import dispatch

    monkeypatch.chdir(tmp_path)
    for argv in (["equip", "discover", "--help"], ["hooks", "--help"], ["init", "-h"]):
        code = dispatch(argv)
        out = capsys.readouterr().out
        assert code == 0, f"{argv} should exit 0"
        assert out.strip(), f"{argv} printed nothing"


@pytest.mark.unit
def test_onboard_help_documents_depth_command_depths_and_wired(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`onboard --help` documents the per-command depth + wiring config keys
    (mirrors the `--skill-only` usage-help substring test)."""
    from dummyindex.cli import dispatch

    monkeypatch.chdir(tmp_path)
    code = dispatch(["onboard", "--help"])
    out = capsys.readouterr().out
    assert code == 0
    assert "--depth" in out
    assert "command_depths" in out
    assert "wired" in out


@pytest.mark.unit
def test_onboard_module_docstring_documents_depth_and_wired() -> None:
    """The onboard handler's own usage banner (module docstring) documents the
    hand-edited `command_depths`/`wired` keys + the `--depth` flag."""
    from dummyindex.cli import onboard

    banner = onboard.__doc__ or ""
    assert "--depth" in banner
    assert "command_depths" in banner
    assert "wired" in banner


@pytest.mark.unit
def test_gc_help_lists_all_four_verbs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`gc --help` documents every verb (status|delete|stamp|signal)."""
    from dummyindex.cli import dispatch

    monkeypatch.chdir(tmp_path)
    code = dispatch(["gc", "--help"])
    out = capsys.readouterr().out
    assert code == 0
    for verb in ("status", "delete", "stamp", "signal"):
        assert verb in out, f"`gc --help` does not document the {verb!r} verb"


@pytest.mark.unit
def test_managed_doc_home_verbs_answer_help(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`migrate-docs --help` and `guard-doc-write --help` each dispatch, exit 0,
    and name the verb (mirrors `test_gc_help_lists_all_four_verbs`)."""
    from dummyindex.cli import dispatch

    monkeypatch.chdir(tmp_path)
    for verb in ("migrate-docs", "guard-doc-write"):
        code = dispatch([verb, "--help"])
        out = capsys.readouterr().out
        assert code == 0, f"`context {verb} --help` should exit 0, got {code}"
        assert out.strip(), f"`context {verb} --help` printed nothing"
        assert verb in out, f"`context {verb} --help` does not name the {verb!r} verb"


@pytest.mark.integration
def test_migrate_stray_docs_playbook_exists() -> None:
    """The migrate-stray-docs playbook exists, is non-empty, and carries the
    "commit the move alone" / `git log --follow` history note."""
    from tests.paths import REPO_ROOT

    playbook = REPO_ROOT / ".context" / "playbooks" / "migrate-stray-docs.md"
    assert playbook.is_file(), f"missing playbook: {playbook}"
    text = playbook.read_text(encoding="utf-8")
    assert text.strip(), "migrate-stray-docs playbook is empty"
    assert "commit the move alone" in text, (
        "playbook must tell the reader to commit the move alone"
    )
    assert "git log --follow" in text, (
        "playbook must name `git log --follow` as the reason"
    )


@pytest.mark.unit
def test_top_level_install_uninstall_and_ingest_help(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Top-level mutating commands answer help without running their handler."""
    from dummyindex import __main__

    monkeypatch.setattr(
        __main__,
        "install",
        lambda **kw: pytest.fail("install --help must not run install"),
    )
    monkeypatch.setattr(__main__.sys, "argv", ["dummyindex", "install", "--help"])
    with pytest.raises(SystemExit) as exc:
        __main__.main()
    assert exc.value.code == 0
    install_help = capsys.readouterr().out
    assert "usage: dummyindex install" in install_help
    assert (
        "--no-default-plugins   skip all default Claude plugins for this run"
        in install_help
    )
    assert (
        "--no-superpowers       compatibility alias for --no-default-plugins"
        in install_help
    )

    monkeypatch.setattr(
        __main__,
        "uninstall",
        lambda **kw: pytest.fail("uninstall --help must not run uninstall"),
    )
    monkeypatch.setattr(__main__.sys, "argv", ["dummyindex", "uninstall", "--help"])
    with pytest.raises(SystemExit) as uninstall_exc:
        __main__.main()
    assert uninstall_exc.value.code == 0
    uninstall_help = capsys.readouterr().out
    assert "usage: dummyindex uninstall" in uninstall_help
    assert "--skill-only" not in uninstall_help

    monkeypatch.setattr(__main__.sys, "argv", ["dummyindex", "ingest", "--help"])
    code = None
    with pytest.raises(SystemExit) as exc2:
        __main__.main()
    code = exc2.value.code
    assert code == 0
    out = capsys.readouterr().out
    assert "Usage: dummyindex context init [args]" in out
    assert "init [path] [--root DIR] [--no-hooks] [--no-default-plugins]" in out
    assert "--no-superpowers is its compatibility alias;" in out
    assert "active Codex project instruction file" in out
    assert "both (default: claude)" in out


@pytest.mark.unit
def test_context_init_help_pins_default_plugin_flag_and_host_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Direct context-init help agrees with the top-level ingest alias."""
    from dummyindex.cli import dispatch

    monkeypatch.chdir(tmp_path)
    assert dispatch(["init", "--help"]) == 0
    out = capsys.readouterr().out
    assert "Usage: dummyindex context init [args]" in out
    assert "init [path] [--root DIR] [--no-hooks] [--no-default-plugins]" in out
    assert "--no-superpowers is its compatibility alias;" in out
    assert "chooses Claude Code guidance/hooks" in out
    assert "active Codex project instruction file" in out
    assert "both (default: claude)" in out


@pytest.mark.unit
def test_context_init_help_uses_current_platform_selector(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`context init --help` shows the Wave 2 selector (``claude|agents|both``),
    not the pre-Wave-2 ``claude|codex|both`` — the top-level help and the
    `cli/init.py` validation error already made this switch; `_USAGE_TEMPLATE`
    must agree."""
    from dummyindex.cli import dispatch

    monkeypatch.chdir(tmp_path)
    assert dispatch(["init", "--help"]) == 0
    out = capsys.readouterr().out
    assert "--platform claude|agents|both" in out
    assert "--platform claude|codex|both" not in out


@pytest.mark.unit
def test_ingest_help_uses_current_platform_selector(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`ingest --help` (the top-level alias for `context init`) shows the
    same Wave 2 selector, never the retired ``claude|codex|both`` spelling."""
    from dummyindex import __main__

    monkeypatch.setattr(__main__.sys, "argv", ["dummyindex", "ingest", "--help"])
    with pytest.raises(SystemExit) as exc:
        __main__.main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--platform claude|agents|both" in out
    assert "--platform claude|codex|both" not in out
