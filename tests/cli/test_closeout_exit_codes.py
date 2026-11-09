"""CLI closeout/learning commands exit non-zero only on a failed learning status.

The CLI has no learner seam, so the stored learning event that closeout reads
on re-run is seeded through the real event file: a stale identity makes the
real learner fail; an evaluated/blocked verdict is a settled status.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.cli import dispatch
from dummyindex.context.domains.evolve_learning import _path as event_path
from dummyindex.context.domains.proposals.retirement import (
    ADMIN_FILES,
    workspace_inventory,
)

_BLOCKED = {"state": "evaluated", "verdict": "blocked", "status": "blocked"}
_FAILED = {"identity": "stale-identity"}


def _workspace(tmp_path: Path, kind: str) -> Path:
    context = tmp_path / ".context"
    workspace = context / ("proposals" if kind == "proposal" else "audits") / "work"
    workspace.mkdir(parents=True)
    if kind == "proposal":
        (workspace / "proposal.json").write_text(
            json.dumps({"slug": "work", "status": "in_progress"}), encoding="utf-8"
        )
        (workspace / "checklist.md").write_text("- [x] Do it\n", encoding="utf-8")
    (context / "conventions").mkdir()
    (context / "conventions" / "coding.md").write_text("# Rules\n", encoding="utf-8")
    (workspace / "lesson.md").write_text("Use the shared parser.\n", encoding="utf-8")
    return workspace


def _write_manifest(workspace: Path, path: Path) -> None:
    inventory = workspace_inventory(workspace)
    transfers = [
        {
            "kind": "lesson",
            "source": "lesson.md",
            "target": ".context/conventions/coding.md",
        }
    ]
    discarded = {
        name: "Reviewed; nothing durable remains"
        for name in inventory
        if name not in ADMIN_FILES and name != "lesson.md"
    }
    manifest = {
        "state": "implemented",
        "reviewed_files": inventory,
        "transfers": transfers,
        "discarded": discarded,
    }
    path.write_text(json.dumps(manifest), encoding="utf-8")


def _argv(kind: str, manifest: Path) -> list[str]:
    if kind == "proposal":
        return ["build", "--proposal", "work", "--closeout", str(manifest)]
    return [
        *("gc", "closeout", "--kind", "audit", "--slug", "work"),
        *("--manifest", str(manifest)),
    ]


def _event_files(root: Path) -> list[Path]:
    return [
        p
        for p in (root / ".context/gc/learning").glob("*.json")
        if not p.name.endswith(".failed.json")
    ]


@pytest.mark.integration
@pytest.mark.parametrize("kind", ["proposal", "audit"])
@pytest.mark.parametrize(
    ("patch", "status", "code"), [(_BLOCKED, "blocked", 0), (_FAILED, "failed", 1)]
)
def test_closeout_exit_code_follows_learning_status(
    tmp_path: Path, capsys, kind: str, patch: dict, status: str, code: int
) -> None:
    workspace = _workspace(tmp_path, kind)
    manifest = tmp_path / "m.json"

    def run() -> int:
        _write_manifest(workspace, manifest)
        return dispatch([*_argv(kind, manifest), "--root", str(tmp_path)])

    assert run() == 0
    (event,) = _event_files(tmp_path)
    stored = json.loads(event.read_text(encoding="utf-8"))
    event.write_text(json.dumps({**stored, **patch}), encoding="utf-8")
    capsys.readouterr()

    assert run() == code
    assert f"learning: {status}" in capsys.readouterr().out


@pytest.mark.integration
@pytest.mark.parametrize(
    ("event", "status", "code"),
    [
        (_BLOCKED, "blocked", 0),
        ({"state": "evaluated", "status": "failed", "error": "boom"}, "failed", 1),
    ],
)
def test_evolve_learning_exit_code_follows_status(
    tmp_path: Path, capsys, event: dict, status: str, code: int
) -> None:
    context = tmp_path / ".context"
    context.mkdir()
    path = event_path(context, "e1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(event), encoding="utf-8")

    argv = ["evolve", "learning", "--event", "e1", "--no-entry"]
    rc = dispatch([*argv, "--root", str(tmp_path)])

    assert rc == code
    assert f"learning: {status}" in capsys.readouterr().err
