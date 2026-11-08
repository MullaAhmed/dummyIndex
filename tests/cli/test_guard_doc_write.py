"""Citation guard: Write/Edit/MultiEdit adding disposable citations to authored docs."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

import dummyindex.cli.guard_doc_write as guard

CITE = ".context/proposals/foo-bar/spec.md"
DOC = ".context/features/x/spec.md"
TOOLS = ["Write", "Edit", "MultiEdit"]


def _payload(tool: str, path: str, text: object) -> dict:
    if tool == "Write":
        ti = {"file_path": path, "content": text}
    elif tool == "Edit":
        ti = {"file_path": path, "old_string": "a", "new_string": text}
    else:
        ti = {"file_path": path, "edits": [{"old_string": "a", "new_string": text}]}
    return {"tool_name": tool, "tool_input": ti}


def _run(repo: Path, monkeypatch, capsys, payload: object) -> str:
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
    assert guard.run(["--root", str(repo)]) == 0
    return capsys.readouterr().out


def _seed(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _denied(out: str) -> bool:
    if not out:
        return False
    return json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.unit
@pytest.mark.parametrize("tool", TOOLS)
def test_denies_added_citation(tool, tmp_path, monkeypatch, capsys):
    repo = tmp_path.resolve()
    payload = _payload(tool, str(repo / DOC), f"see {CITE}")
    out = _run(repo, monkeypatch, capsys, payload)
    assert _denied(out)
    assert "proposals/foo-bar/" in out


@pytest.mark.unit
@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize(
    "rel",
    [
        ".context/PROJECT.md",
        ".context/conventions/testing.md",
        ".context/architecture/overview.md",
    ],
)
def test_denies_other_authored_docs(tool, rel, tmp_path, monkeypatch, capsys):
    repo = tmp_path.resolve()
    out = _run(repo, monkeypatch, capsys, _payload(tool, str(repo / rel), CITE))
    assert _denied(out)


@pytest.mark.unit
@pytest.mark.parametrize("tool", TOOLS)
def test_denies_windows_separators(tool, tmp_path, monkeypatch, capsys):
    repo = tmp_path.resolve()
    path = str(repo / DOC).replace("/", "\\")
    text = "see .context\\proposals\\foo-bar\\spec.md"
    assert _denied(_run(repo, monkeypatch, capsys, _payload(tool, path, text)))


@pytest.mark.unit
@pytest.mark.parametrize("tool", TOOLS)
def test_denies_relative_path(tool, tmp_path, monkeypatch, capsys):
    repo = tmp_path.resolve()
    assert _denied(_run(repo, monkeypatch, capsys, _payload(tool, DOC, CITE)))


@pytest.mark.unit
@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize(
    "rel",
    [
        ".context/proposals/foo-bar/spec.md",
        ".context/features/x/council/notes.md",
        ".context/features/x/data.json",
        ".context/conventions/naming.md",
        "docs/guide.md",
    ],
)
def test_allows_excluded_paths(tool, rel, tmp_path, monkeypatch, capsys):
    repo = tmp_path.resolve()
    assert _run(repo, monkeypatch, capsys, _payload(tool, str(repo / rel), CITE)) == ""


@pytest.mark.unit
@pytest.mark.parametrize("tool", TOOLS)
def test_allows_existing_citation(tool, tmp_path, monkeypatch, capsys):
    repo = tmp_path.resolve()
    _seed(repo, DOC, f"old {CITE}\n")
    payload = _payload(tool, str(repo / DOC), f"again {CITE}")
    assert _run(repo, monkeypatch, capsys, payload) == ""


@pytest.mark.unit
def test_edit_only_new_citation_counts(tmp_path, monkeypatch, capsys):
    repo = tmp_path.resolve()
    _seed(repo, DOC, f"old {CITE}\n")
    text = f"{CITE} and .context/audits/other/plan.md"
    payload = _payload("Edit", str(repo / DOC), text)
    assert _denied(_run(repo, monkeypatch, capsys, payload))


@pytest.mark.unit
@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize("bad", [None, 5, ["x"], {"a": 1}])
def test_non_string_content_allows(tool, bad, tmp_path, monkeypatch, capsys):
    repo = tmp_path.resolve()
    assert _run(repo, monkeypatch, capsys, _payload(tool, str(repo / DOC), bad)) == ""


@pytest.mark.unit
@pytest.mark.parametrize("tool", TOOLS)
def test_oversized_allows(tool, tmp_path, monkeypatch, capsys):
    repo = tmp_path.resolve()
    text = CITE + "x" * guard.MAX_SCAN_CHARS
    assert _run(repo, monkeypatch, capsys, _payload(tool, str(repo / DOC), text)) == ""


@pytest.mark.unit
def test_multiedit_bad_edits_ignored(tmp_path, monkeypatch, capsys):
    repo = tmp_path.resolve()
    payload = {
        "tool_name": "MultiEdit",
        "tool_input": {
            "file_path": str(repo / DOC),
            "edits": ["x", None, {"new_string": 3}],
        },
    }
    assert _run(repo, monkeypatch, capsys, payload) == ""


@pytest.mark.unit
def test_multiedit_second_edit_denied(tmp_path, monkeypatch, capsys):
    repo = tmp_path.resolve()
    payload = {
        "tool_name": "MultiEdit",
        "tool_input": {
            "file_path": str(repo / DOC),
            "edits": [{"new_string": "clean"}, {"new_string": CITE}],
        },
    }
    assert _denied(_run(repo, monkeypatch, capsys, payload))


@pytest.mark.unit
@pytest.mark.parametrize("raw", ["", "{ nope", "[]", '{"tool_name":"Edit"}'])
def test_malformed_allows(raw, tmp_path, monkeypatch, capsys):
    assert _run(tmp_path.resolve(), monkeypatch, capsys, raw) == ""


@pytest.mark.unit
def test_exception_allows(tmp_path, monkeypatch, capsys):
    repo = tmp_path.resolve()

    def boom(*_a, **_k):
        raise RuntimeError("x")

    monkeypatch.setattr(
        "dummyindex.context.domains.docguard.citations.added_citations", boom
    )
    payload = _payload("Edit", str(repo / DOC), CITE)
    assert _run(repo, monkeypatch, capsys, payload) == ""


@pytest.mark.unit
def test_citation_exception_still_runs_stray_doc_check(tmp_path, monkeypatch, capsys):
    repo = tmp_path.resolve()

    def boom(*_a, **_k):
        raise RuntimeError("x")

    monkeypatch.setattr(guard, "_citation_deny", boom)
    payload = _payload("Write", str(repo / "docs/plans/stray.md"), "x")
    out = _run(repo, monkeypatch, capsys, payload)
    assert _denied(out)


@pytest.mark.unit
def test_edit_split_citation_denied(tmp_path, monkeypatch, capsys):
    repo = tmp_path.resolve()
    _seed(repo, DOC, "see .context/proposals/\n")
    payload = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(repo / DOC),
            "old_string": "proposals/\n",
            "new_string": "proposals/foo-bar/\n",
        },
    }
    assert _denied(_run(repo, monkeypatch, capsys, payload))


@pytest.mark.unit
def test_edit_completing_split_citation_denied(tmp_path, monkeypatch, capsys):
    repo = tmp_path.resolve()
    _seed(repo, DOC, "see .context/proposals/foo-XX/spec.md\n")
    ti = {"file_path": str(repo / DOC), "old_string": "XX", "new_string": "bar"}
    out = _run(repo, monkeypatch, capsys, {"tool_name": "Edit", "tool_input": ti})
    assert _denied(out)


@pytest.mark.unit
def test_multiedit_completing_split_citation_denied(tmp_path, monkeypatch, capsys):
    repo = tmp_path.resolve()
    _seed(repo, DOC, "see .context/proposals/foo-XX/spec.md\n")
    edits = [{"old_string": "XX", "new_string": "bar"}]
    ti = {"file_path": str(repo / DOC), "edits": edits}
    out = _run(repo, monkeypatch, capsys, {"tool_name": "MultiEdit", "tool_input": ti})
    assert _denied(out)


LANG_TOOLS = ["Agent", "Task", "SendMessage"]
ENGLISH = (
    "Implement the feature across the parser module and update the tests accordingly. "
    * 5
)
CHINESE = "请在解析模块中实现这个功能并同步更新相关测试，保持代码与命令原样。" * 10


def _lang_field(tool: str) -> str:
    return "message" if tool == "SendMessage" else "prompt"


def _lang_payload(tool: str, text: object) -> dict:
    return {"tool_name": tool, "tool_input": {_lang_field(tool): text}}


@pytest.mark.unit
@pytest.mark.parametrize("tool", LANG_TOOLS)
def test_language_hint_warns_english(tool, tmp_path, monkeypatch, capsys):
    repo = tmp_path.resolve()
    out = _run(repo, monkeypatch, capsys, _lang_payload(tool, ENGLISH))
    lines = out.splitlines()
    assert len(lines) == 1
    hso = json.loads(lines[0])["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse"
    assert "additionalContext" in hso
    assert "permissionDecision" not in hso


@pytest.mark.unit
@pytest.mark.parametrize("tool", LANG_TOOLS)
def test_language_hint_silent_for_chinese(tool, tmp_path, monkeypatch, capsys):
    repo = tmp_path.resolve()
    assert _run(repo, monkeypatch, capsys, _lang_payload(tool, CHINESE)) == ""


@pytest.mark.unit
@pytest.mark.parametrize("tool", LANG_TOOLS)
def test_language_hint_silent_for_short_english(tool, tmp_path, monkeypatch, capsys):
    repo = tmp_path.resolve()
    assert _run(repo, monkeypatch, capsys, _lang_payload(tool, "short english")) == ""


@pytest.mark.unit
@pytest.mark.parametrize("tool", LANG_TOOLS)
@pytest.mark.parametrize("bad", [None, 5, ["x"], {"a": 1}])
def test_language_hint_non_string_field_allows(
    tool, bad, tmp_path, monkeypatch, capsys
):
    repo = tmp_path.resolve()
    assert _run(repo, monkeypatch, capsys, _lang_payload(tool, bad)) == ""


@pytest.mark.unit
@pytest.mark.parametrize("tool", LANG_TOOLS)
@pytest.mark.parametrize("ti", [None, "text", ["x"]])
def test_language_hint_non_dict_input_allows(tool, ti, tmp_path, monkeypatch, capsys):
    repo = tmp_path.resolve()
    payload = {"tool_name": tool, "tool_input": ti}
    assert _run(repo, monkeypatch, capsys, payload) == ""


@pytest.mark.unit
@pytest.mark.parametrize("tool", LANG_TOOLS)
def test_language_hint_missing_field_allows(tool, tmp_path, monkeypatch, capsys):
    repo = tmp_path.resolve()
    payload = {"tool_name": tool, "tool_input": {"other": ENGLISH}}
    assert _run(repo, monkeypatch, capsys, payload) == ""


@pytest.mark.unit
@pytest.mark.parametrize("tool", LANG_TOOLS)
def test_language_hint_oversized_allows(tool, tmp_path, monkeypatch, capsys):
    repo = tmp_path.resolve()
    text = ENGLISH + "x" * guard.MAX_SCAN_CHARS
    assert _run(repo, monkeypatch, capsys, _lang_payload(tool, text)) == ""


@pytest.mark.unit
@pytest.mark.parametrize("tool", LANG_TOOLS)
def test_language_hint_malformed_stdin_allows(tool, tmp_path, monkeypatch, capsys):
    assert _run(tmp_path.resolve(), monkeypatch, capsys, "not json") == ""


@pytest.mark.unit
@pytest.mark.parametrize("tool", LANG_TOOLS)
def test_language_hint_still_warns_when_doc_guard_disabled(
    tool, tmp_path, monkeypatch, capsys
):
    repo = tmp_path.resolve()
    _seed(repo, ".context/config.json", '{"doc_guard_enabled": false}')
    out = _run(repo, monkeypatch, capsys, _lang_payload(tool, ENGLISH))
    hso = json.loads(out)["hookSpecificOutput"]
    assert "additionalContext" in hso
    assert "permissionDecision" not in hso
