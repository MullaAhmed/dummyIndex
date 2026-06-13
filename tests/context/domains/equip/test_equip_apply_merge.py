"""`equip apply` / `add-specialist` must MERGE with the prior manifest.

REGRESSION (audit 2026-06-13, C2-P0): `_apply_write` used to rebuild
equipment.json from scratch — every MARKETPLACE plugin record, VENDORED skill,
and INSTALLED (adopted) entry silently vanished on the next apply while staying
live in .claude/settings.json / on disk. The contract is never-silently-drop:
foreign records carry forward verbatim; a re-derived adoption replaces (never
duplicates) its prior record; this run's hook records replace prior same-name
hook records.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.cli.equip import project_slug, run as run_equip


def _project(tmp_path: Path, languages: list[str]) -> Path:
    context_dir = tmp_path / ".context"
    files = [
        {"path": f"src/f{i}.x", "language": lang, "size_bytes": 10}
        for i, lang in enumerate(languages)
    ]
    (context_dir / "map").mkdir(parents=True, exist_ok=True)
    (context_dir / "map" / "files.json").write_text(
        json.dumps({"schema_version": 1, "files": files}) + "\n", encoding="utf-8"
    )
    (context_dir / "conventions").mkdir(parents=True, exist_ok=True)
    (context_dir / "conventions" / "naming.md").write_text("# naming\n", encoding="utf-8")
    return tmp_path


def _manifest(root: Path) -> dict:
    return json.loads((root / ".context" / "equipment.json").read_text(encoding="utf-8"))


def _write_manifest(root: Path, data: dict) -> None:
    (root / ".context" / "equipment.json").write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )


_MARKETPLACE_RECORD = {
    "kind": "plugin",
    "name": "pg-tuner@official",
    "path": ".claude/settings.json",
    "source": "marketplace",
    "capabilities": ["database"],
    "grounded_in": [],
    "subagent_type": None,
    "version": "1.2.0",
    "origin_hash": None,
    "marketplace": "official",
    "origin_repo": "anthropics/claude-plugins-official",
    "origin_ref": None,
    "mechanism": "native",
}

_VENDORED_RECORD = {
    "kind": "skill",
    "name": "pdf-extract",
    "path": ".claude/skills/pdf-extract/SKILL.md",
    "source": "vendored",
    "capabilities": ["docs"],
    "grounded_in": [],
    "subagent_type": None,
    "version": None,
    "origin_hash": "sha256:deadbeef",
    "marketplace": "skills",
    "origin_repo": "anthropics/skills",
    "origin_ref": "abc123",
    "mechanism": "vendor",
}

_INSTALLED_RECORD = {
    "kind": "agent",
    "name": "Data Engineer",
    "path": "",
    "source": "installed",
    "capabilities": ["database", "data"],
    "grounded_in": [],
    "subagent_type": "Data Engineer",
    "version": None,
    "origin_hash": None,
    "marketplace": None,
    "origin_repo": None,
    "origin_ref": None,
    "mechanism": None,
}


def _seed_foreign_records(root: Path) -> None:
    data = _manifest(root)
    data["items"].extend([_MARKETPLACE_RECORD, _VENDORED_RECORD, _INSTALLED_RECORD])
    _write_manifest(root, data)


@pytest.mark.integration
def test_reapply_keeps_marketplace_vendored_and_installed_records(tmp_path: Path) -> None:
    root = _project(tmp_path, ["python", "python"])
    assert run_equip([str(root)]) == 0
    _seed_foreign_records(root)

    assert run_equip([str(root)]) == 0  # re-apply must merge, not rebuild

    by_name = {(i["name"], i["source"]) for i in _manifest(root)["items"]}
    assert ("pg-tuner@official", "marketplace") in by_name
    assert ("pdf-extract", "vendored") in by_name
    assert ("Data Engineer", "installed") in by_name
    assert ("python-implementer", "generated") in by_name


@pytest.mark.integration
def test_foreign_records_carried_verbatim(tmp_path: Path) -> None:
    root = _project(tmp_path, ["python"])
    assert run_equip([str(root)]) == 0
    _seed_foreign_records(root)
    assert run_equip([str(root)]) == 0
    items = {i["name"]: i for i in _manifest(root)["items"]}
    assert items["pg-tuner@official"] == _MARKETPLACE_RECORD
    assert items["pdf-extract"] == _VENDORED_RECORD
    assert items["Data Engineer"] == _INSTALLED_RECORD


@pytest.mark.integration
def test_add_specialist_keeps_foreign_records(tmp_path: Path) -> None:
    root = _project(tmp_path, ["python"])
    assert run_equip([str(root)]) == 0
    _seed_foreign_records(root)
    assert run_equip(["add-specialist", "database", "--root", str(root)]) == 0
    names = {i["name"] for i in _manifest(root)["items"]}
    assert {"pg-tuner@official", "pdf-extract", "Data Engineer"} <= names
    assert f"{project_slug(root)}-db-specialist" in names


@pytest.mark.integration
def test_stale_generated_record_carried_forward_not_dropped(tmp_path: Path) -> None:
    # A generated record whose name this run does not re-render (e.g. the stack
    # label changed) is carried forward verbatim — never silently dropped.
    root = _project(tmp_path, ["python"])
    assert run_equip([str(root)]) == 0
    data = _manifest(root)
    stale = dict(data["items"][0])
    stale["name"] = "rust-implementer"
    stale["path"] = ".claude/agents/rust-implementer.md"
    data["items"].append(stale)
    _write_manifest(root, data)

    assert run_equip([str(root)]) == 0
    names = [i["name"] for i in _manifest(root)["items"]]
    assert "rust-implementer" in names


@pytest.mark.integration
def test_rederived_adoption_never_duplicates(tmp_path: Path) -> None:
    # A --for-proposal run that re-derives an existing adoption must end with
    # exactly ONE record for it.
    root = _project(tmp_path, ["javascript", "javascript"])
    prop = root / ".context" / "proposals" / "add-ui"
    prop.mkdir(parents=True)
    (prop / "plan.md").write_text("# Plan\n\nAdd a React frontend with CSS.\n", encoding="utf-8")
    (prop / "checklist.md").write_text("- [ ] build the UI\n", encoding="utf-8")

    assert run_equip([str(root), "--for-proposal", "add-ui"]) == 0
    assert run_equip([str(root), "--for-proposal", "add-ui"]) == 0  # re-derive

    names = [i["name"] for i in _manifest(root)["items"]]
    frontend = [n for n in names if n == "Frontend Developer"]
    assert len(frontend) == 1
    assert len(names) == len(set(names))  # no duplicate entries at all


@pytest.mark.integration
def test_hook_records_do_not_duplicate_across_reapplies(tmp_path: Path) -> None:
    root = _project(tmp_path, ["python"])
    (root / "pyproject.toml").write_text("[tool.ruff]\n", encoding="utf-8")
    assert run_equip([str(root)]) == 0
    assert run_equip([str(root)]) == 0
    hooks = [i for i in _manifest(root)["items"] if i["kind"] == "hook"]
    assert len(hooks) == 1


@pytest.mark.integration
def test_adoption_printed_in_non_dry_run_output(tmp_path: Path, capsys) -> None:
    # Quick win (evidence: "i dont see them under .claude"): a manifest-only
    # adoption is announced in the apply output, mirroring the dry-run wording.
    root = _project(tmp_path, ["javascript"])
    prop = root / ".context" / "proposals" / "add-ui"
    prop.mkdir(parents=True)
    (prop / "plan.md").write_text("# Plan\n\nReact frontend.\n", encoding="utf-8")
    capsys.readouterr()
    assert run_equip([str(root), "--for-proposal", "add-ui"]) == 0
    out = capsys.readouterr().out
    assert "adopt" in out
    assert "Frontend Developer" in out


@pytest.mark.integration
def test_summary_counts_file_writes_not_records(tmp_path: Path, capsys) -> None:
    # Quick win (evidence 12): the summary line must count actual FILE writes —
    # not carried-forward records, manifest-only adoptions, or hook records.
    root = _project(tmp_path, ["python"])
    (root / "pyproject.toml").write_text("[tool.ruff]\n", encoding="utf-8")
    capsys.readouterr()
    assert run_equip([str(root)]) == 0
    out = capsys.readouterr().out
    # 4 generated files (implementer/tester/reviewer/verify); the hook is a
    # record, not a file write.
    assert "wrote 4 file(s)" in out


@pytest.mark.integration
def test_apply_json_reports_carried_forward(tmp_path: Path, capsys) -> None:
    root = _project(tmp_path, ["python"])
    assert run_equip([str(root)]) == 0
    _seed_foreign_records(root)
    capsys.readouterr()
    assert run_equip(["--json", str(root)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert {"pg-tuner@official", "pdf-extract", "Data Engineer"} <= set(
        payload["carried_forward"]
    )


# ----- duplicate-entry defect: equip's own files must never be re-adopted ----


@pytest.mark.integration
def test_generated_reviewer_not_readopted_as_project_agent(tmp_path: Path) -> None:
    # REGRESSION (audit C2-P1): a repo dir named `frontend` makes the generated
    # reviewer literally `frontend-reviewer`; a frontend proposal then re-adopted
    # that same file as a project agent — two conflicting records for one path.
    root = _project(tmp_path / "frontend", ["javascript", "javascript"])
    root.mkdir(parents=True, exist_ok=True)
    assert run_equip([str(root)]) == 0  # writes .claude/agents/frontend-reviewer.md

    prop = root / ".context" / "proposals" / "add-ui"
    prop.mkdir(parents=True)
    (prop / "plan.md").write_text("# Plan\n\nReact frontend with CSS.\n", encoding="utf-8")
    assert run_equip([str(root), "--for-proposal", "add-ui"]) == 0

    entries = [i for i in _manifest(root)["items"] if i["name"] == "frontend-reviewer"]
    assert len(entries) == 1
    assert entries[0]["source"] == "generated"


@pytest.mark.integration
def test_user_authored_project_agent_still_adopted(tmp_path: Path) -> None:
    # A genuinely user-authored .claude/agents file (no sentinel) keeps being
    # adopted with its real path — the filter only excludes equip's own output.
    root = _project(tmp_path, ["javascript"])
    agents = root / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "ui-wizard.md").write_text("# my own frontend agent\n", encoding="utf-8")
    prop = root / ".context" / "proposals" / "add-ui"
    prop.mkdir(parents=True)
    (prop / "plan.md").write_text("# Plan\n\nReact frontend with CSS.\n", encoding="utf-8")

    assert run_equip([str(root), "--for-proposal", "add-ui"]) == 0
    item = next(i for i in _manifest(root)["items"] if i["name"] == "ui-wizard")
    assert item["source"] == "installed"
    assert item["path"] == ".claude/agents/ui-wizard.md"


@pytest.mark.unit
def test_drop_generated_stems_filters_sentinel_and_manifest_names(tmp_path: Path) -> None:
    from dummyindex.cli.equip.common import drop_generated_stems
    from dummyindex.context.domains.equip import (
        GENERATED_SENTINEL,
        EquipmentItem,
        EquipmentKind,
        EquipmentManifest,
        EquipmentSource,
    )

    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "frontend-reviewer.md").write_text(
        f"---\nname: frontend-reviewer\n---\n{GENERATED_SENTINEL}\n", encoding="utf-8"
    )
    (agents / "lost-generated.md").write_text(
        f"body\n{GENERATED_SENTINEL}\n", encoding="utf-8"  # record lost, sentinel survives
    )
    (agents / "ui-wizard.md").write_text("# user-authored\n", encoding="utf-8")
    prior = EquipmentManifest(
        schema_version=4,
        items=(
            EquipmentItem(
                kind=EquipmentKind.AGENT,
                name="frontend-reviewer",
                path=".claude/agents/frontend-reviewer.md",
                source=EquipmentSource.GENERATED,
            ),
        ),
    )
    kept = drop_generated_stems(
        tmp_path, prior, ("frontend-reviewer", "lost-generated", "ui-wizard")
    )
    assert kept == ("ui-wizard",)
