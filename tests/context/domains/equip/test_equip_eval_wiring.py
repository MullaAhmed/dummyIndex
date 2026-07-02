"""Tests for the two additive, never-clobber eval wirings (Task 15).

Both wirings are stretch — they must be strictly additive and never change the
existing ``equip apply`` / ``equip status`` output shape or break an existing
equip test:

- ``StatusReport.unevaluated`` — a new frozen-dataclass channel (default ``()``),
  populated ONLY at the CLI status handler by globbing the evals dir. The pure
  ``status()`` never touches it; ``ItemState`` is untouched.
- ``seed_starter_suites`` — ``equip apply`` seeds a schema-valid starter
  ``<tool>.suite.json`` per generated tool under the atomic never-clobber guard,
  silently (no stdout/JSON change).
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from dummyindex.cli.equip import dispatch
from dummyindex.cli.equip.seed import seed_starter_suites, starter_suite_cases
from dummyindex.context.domains.atomic_io import write_text_atomic
from dummyindex.context.domains.equip import (
    SCHEMA_VERSION,
    EquipmentItem,
    EquipmentManifest,
    content_hash,
    write_manifest,
)
from dummyindex.context.domains.equip.enums import EquipmentKind, EquipmentSource
from dummyindex.context.domains.equip.eval import parse_eval_suite
from dummyindex.context.domains.equip.lifecycle.status import StatusReport

_EVALS_REL = "equipment-evals"

_TOOL = "python-implementer"
_TOOL_REL = ".claude/agents/python-implementer.md"
_TOOL_BODY = "---\nname: python-implementer\nversion: 1.0.0\n---\n<!-- dummyindex:generated -->\nbody\n"


# ----- fixture helpers ------------------------------------------------------


def _managed_item(
    name: str = _TOOL,
    rel: str = _TOOL_REL,
    body: str = _TOOL_BODY,
    *,
    capabilities: tuple[str, ...] = ("implement",),
) -> EquipmentItem:
    """A generated, file-backed, hash-baselined item (is_lifecycle_managed True)."""
    return EquipmentItem(
        kind=EquipmentKind.AGENT,
        name=name,
        path=rel,
        source=EquipmentSource.GENERATED,
        capabilities=capabilities,
        version="1.0.0",
        origin_hash=content_hash(body),
    )


def _equipped_root(tmp_path: Path, item: EquipmentItem) -> Path:
    """Write one managed item's file + a manifest under ``tmp_path`` and return it."""
    write_text_atomic(tmp_path / item.path, _TOOL_BODY)
    write_manifest(
        tmp_path / ".context",
        EquipmentManifest(schema_version=SCHEMA_VERSION, items=(item,)),
    )
    return tmp_path


def _evals_dir(root: Path) -> Path:
    return root / ".context" / _EVALS_REL


# ----- A) StatusReport.unevaluated field ------------------------------------


@pytest.mark.unit
def test_status_report_unevaluated_defaults_empty() -> None:
    """The new channel defaults to an empty tuple (additive; no shape change)."""
    assert StatusReport().unevaluated == ()


@pytest.mark.unit
def test_status_report_unevaluated_round_trips_through_replace() -> None:
    """`dataclasses.replace` carries the new field on the frozen dataclass."""
    base = StatusReport()
    replaced = dataclasses.replace(base, unevaluated=("a", "b"))
    assert replaced.unevaluated == ("a", "b")
    # Untouched fields keep their defaults — a surgical, additive field.
    assert replaced.items == () and replaced.missing_playbook == ()


# ----- A) run_status surfaces unevaluated tools -----------------------------


@pytest.mark.integration
def test_status_flags_generated_tool_with_no_result_as_unevaluated(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A managed tool with no eval result surfaces under `unevaluated` (JSON + text)."""
    root = _equipped_root(tmp_path, _managed_item())

    capsys.readouterr()  # drain
    assert dispatch.run(["status", "--root", str(root), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["unevaluated"] == [_TOOL]

    # Text output surfaces the same tool on its own `unevaluated` line.
    assert dispatch.run(["status", "--root", str(root)]) == 0
    text = capsys.readouterr().out
    assert "unevaluated" in text and _TOOL in text
    assert "run `equip eval`" in text


@pytest.mark.integration
def test_status_drops_tool_from_unevaluated_once_a_result_exists(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Writing `<tool>.result.json` removes the tool from `unevaluated`."""
    root = _equipped_root(tmp_path, _managed_item())

    # A recorded result — any labelless result file counts as evaluated.
    write_text_atomic(
        _evals_dir(root) / f"{_TOOL}.result.json",
        json.dumps({"tool_name": _TOOL, "accuracy": 1.0}) + "\n",
    )

    capsys.readouterr()
    assert dispatch.run(["status", "--root", str(root), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["unevaluated"] == []


@pytest.mark.integration
def test_status_drops_tool_from_unevaluated_for_a_labelled_run_result(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A labelled `<tool>.run-<L>.result.json` also counts as evaluated."""
    root = _equipped_root(tmp_path, _managed_item())
    write_text_atomic(
        _evals_dir(root) / f"{_TOOL}.run-a.result.json",
        json.dumps({"tool_name": _TOOL, "accuracy": 1.0}) + "\n",
    )

    capsys.readouterr()
    assert dispatch.run(["status", "--root", str(root), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["unevaluated"] == []


# ----- B) seed_starter_suites: schema-valid, never-clobber ------------------


@pytest.mark.unit
def teststarter_suite_cases_are_capability_positives_plus_one_decoy() -> None:
    """Up to two capability positives + a fixed decoy negative; schema-parseable."""
    cases = starter_suite_cases(_TOOL, ("implement", "test", "review"))
    ids = [c.case_id for c in cases]
    # First two capabilities → one positive each; third is dropped.
    assert ids == ["implement-positive", "test-positive", "decoy-negative"]
    assert [c.expects_trigger for c in cases] == [True, True, False]


@pytest.mark.unit
def teststarter_suite_cases_generic_positive_when_no_capabilities() -> None:
    """Empty capabilities still emits one generic positive + the decoy."""
    cases = starter_suite_cases(_TOOL, ())
    assert [c.case_id for c in cases] == ["positive", "decoy-negative"]


@pytest.mark.unit
def testseed_starter_suites_writes_schema_valid_suite(tmp_path: Path) -> None:
    """Seeding writes a `<tool>.suite.json` that `parse_eval_suite` accepts."""
    context_dir = tmp_path / ".context"
    seed_starter_suites(context_dir, (_managed_item(),))

    suite_path = context_dir / _EVALS_REL / f"{_TOOL}.suite.json"
    assert suite_path.is_file(), "a starter suite must be seeded for a managed tool"
    data = json.loads(suite_path.read_text(encoding="utf-8"))
    # Parseable by the pure suite parser — a real, usable starting file.
    cases = parse_eval_suite(data)
    assert any(c.expects_trigger for c in cases)
    assert any(not c.expects_trigger for c in cases)


@pytest.mark.unit
def testseed_starter_suites_skips_non_managed_items(tmp_path: Path) -> None:
    """An adopted (path-less) item is not lifecycle-managed → no suite seeded."""
    context_dir = tmp_path / ".context"
    adopted = EquipmentItem(
        kind=EquipmentKind.AGENT,
        name="Data Engineer",
        path="",  # registry pointer — not file-backed, not managed
        source=EquipmentSource.INSTALLED,
        capabilities=("database",),
    )
    seed_starter_suites(context_dir, (adopted,))
    assert not (context_dir / _EVALS_REL).exists()


@pytest.mark.unit
def testseed_starter_suites_never_clobbers_an_existing_suite(tmp_path: Path) -> None:
    """A hand-authored suite is left byte-for-byte untouched (never-clobber)."""
    context_dir = tmp_path / ".context"
    suite_path = context_dir / _EVALS_REL / f"{_TOOL}.suite.json"
    sentinel = json.dumps(
        {
            "cases": [
                {"case_id": "mine", "prompt": "hand-written", "expects_trigger": True}
            ]
        }
    )
    write_text_atomic(suite_path, sentinel)

    seed_starter_suites(context_dir, (_managed_item(),))

    assert suite_path.read_text(encoding="utf-8") == sentinel


@pytest.mark.unit
def test_seed_starter_suites_skips_unsafe_tool_name(tmp_path: Path) -> None:
    """A traversal manifest name is skipped — no write escapes the evals dir.

    Defense-in-depth mirroring the eval CLI's ``safe_tool_name`` contract: the
    manifest ``name`` becomes a path segment, so a crafted ``../../evil`` must be
    rejected before it can reach ``write_text_atomic`` (whose ``mkdir(parents=…)``
    would otherwise create dirs and write anywhere the process can reach).
    """
    context_dir = tmp_path / ".context"
    evil = _managed_item(name="../../evil", rel=".claude/agents/evil.md")
    seed_starter_suites(context_dir, (evil,))
    assert not list(tmp_path.rglob("*.suite.json")), "unsafe name must not seed a suite"
    assert not list(tmp_path.rglob("*evil*")), "no write escaped the evals dir"


# ----- B) equip apply seeds silently (real integration) ----------------------


@pytest.mark.integration
def test_equip_apply_seeds_starter_suites_for_generated_tools(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A real `equip apply` seeds parseable starter suites without changing output.

    Also proves never-clobber end-to-end: a hand-authored suite written before a
    second apply survives verbatim.
    """
    from dummyindex.cli.equip import run as run_equip
    from dummyindex.context.build.runner import build_all

    (tmp_path / "pyproject.toml").write_text(
        "[tool.ruff]\n[tool.mypy]\n"
        '[project]\nname = "demo"\ndependencies = ["pytest"]\n',
        encoding="utf-8",
    )
    (tmp_path / "uv.lock").write_text("# lock\n", encoding="utf-8")
    (tmp_path / "app.py").write_text(
        "def add(a, b):\n    return a + b\n", encoding="utf-8"
    )
    build_all(tmp_path, out_root=tmp_path, dummyindex_version="test")

    capsys.readouterr()
    assert run_equip(["apply", str(tmp_path)]) == 0
    apply_out = capsys.readouterr().out
    # Silent seeding: the apply summary must NOT mention suites/evals.
    assert "suite" not in apply_out.lower()
    assert "equipment-evals" not in apply_out

    impl_suite = _evals_dir(tmp_path) / f"{_TOOL}.suite.json"
    assert impl_suite.is_file(), "apply must seed a starter suite for a generated tool"
    parse_eval_suite(json.loads(impl_suite.read_text(encoding="utf-8")))

    # Hand-author the suite, re-apply, and assert it is never clobbered.
    mine = json.dumps(
        {
            "cases": [
                {"case_id": "mine", "prompt": "real prompt", "expects_trigger": True}
            ]
        }
    )
    write_text_atomic(impl_suite, mine)
    capsys.readouterr()
    assert run_equip(["apply", str(tmp_path)]) == 0
    assert impl_suite.read_text(encoding="utf-8") == mine
