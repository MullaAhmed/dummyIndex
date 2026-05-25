"""Tests for `dummyindex context enrich-plan` / `enrich-apply` and the
underlying `dummyindex.context.enrich` module."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from dummyindex.cli import dispatch
from dummyindex.context.domains.enrich import (
    apply_updates,
    build_plan,
    write_plan,
)


_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample_repo"


def _ingested(tmp_path: Path, name: str) -> Path:
    target = tmp_path / name
    shutil.copytree(_FIXTURE, target)
    assert dispatch(["init", str(target)]) == 0
    return target


# ----- build_plan ------------------------------------------------------------


@pytest.mark.unit
def test_build_plan_finds_all_stub_nodes(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "plan_all_stubs")
    plan = build_plan(target / ".context")

    assert plan.schema_version == 1
    assert plan.stats["total_nodes"] >= 1
    # Right after `init`, every node is still a deterministic stub.
    assert plan.stats["stub_nodes"] == plan.stats["total_nodes"]
    assert len(plan.nodes) == plan.stats["stub_nodes"]


@pytest.mark.unit
def test_build_plan_groups_into_batches(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "plan_batches")
    plan = build_plan(target / ".context")

    batch_kinds = {b.kind for b in plan.batches}
    # `structure` batch (project + any dirs) plus one `file_subtree` per file.
    assert "structure" in batch_kinds
    assert "file_subtree" in batch_kinds

    # Every node in `plan.nodes` belongs to exactly one batch.
    all_batched_ids = [nid for b in plan.batches for nid in b.node_ids]
    plan_ids = [n.node_id for n in plan.nodes]
    assert sorted(all_batched_ids) == sorted(plan_ids)


@pytest.mark.unit
def test_build_plan_records_evidence_for_in_file_symbols(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "plan_evidence")
    plan = build_plan(target / ".context")

    for node in plan.nodes:
        if node.kind in ("project", "dir"):
            assert node.evidence_files == ()
        elif node.kind == "file":
            # The file node's own path should be its evidence.
            assert node.evidence_files == (node.path,)
        else:
            # Function/class/method: at least one evidence file is recorded,
            # and it matches the symbol's `path` attribute.
            assert len(node.evidence_files) == 1
            assert node.evidence_files[0] == node.path


@pytest.mark.unit
def test_build_plan_skips_already_inferred_nodes(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "plan_skip_inferred")
    tree_path = target / ".context" / "tree.json"
    tree = json.loads(tree_path.read_text(encoding="utf-8"))

    # Flip the project node to INFERRED to simulate prior enrichment.
    tree["root"]["confidence"] = "INFERRED"
    tree_path.write_text(json.dumps(tree, indent=2), encoding="utf-8")

    plan = build_plan(target / ".context")
    assert all(n.node_id != tree["root"]["node_id"] for n in plan.nodes)


@pytest.mark.unit
def test_build_plan_missing_tree_raises(tmp_path: Path) -> None:
    context = tmp_path / "empty" / ".context"
    context.mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        build_plan(context)


@pytest.mark.unit
def test_write_plan_round_trips(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "plan_roundtrip")
    plan = build_plan(target / ".context")

    out = target / ".context" / "_enrich_plan.json"
    write_plan(out, plan)

    raw = json.loads(out.read_text(encoding="utf-8"))
    assert raw["schema_version"] == plan.schema_version
    assert raw["stats"] == plan.stats
    assert len(raw["nodes"]) == len(plan.nodes)
    assert len(raw["batches"]) == len(plan.batches)


# ----- apply_updates ---------------------------------------------------------


@pytest.mark.unit
def test_apply_updates_writes_abstract_and_bumps_confidence(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "apply_basic")
    tree_path = target / ".context" / "tree.json"
    tree = json.loads(tree_path.read_text(encoding="utf-8"))
    root_id = tree["root"]["node_id"]

    result = apply_updates(
        target / ".context", {root_id: "The root of this codebase."}
    )

    assert result.updated == (root_id,)
    assert result.unknown == ()
    after = json.loads(tree_path.read_text(encoding="utf-8"))
    assert after["root"]["abstract"] == "The root of this codebase."
    assert after["root"]["confidence"] == "INFERRED"


@pytest.mark.unit
def test_apply_updates_reports_unknown_ids(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "apply_unknown")
    result = apply_updates(
        target / ".context",
        {"definitely_not_a_node_id": "bogus"},
    )
    assert result.updated == ()
    assert result.unknown == ("definitely_not_a_node_id",)


@pytest.mark.unit
def test_apply_updates_is_idempotent(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "apply_idempotent")
    tree_path = target / ".context" / "tree.json"
    root_id = json.loads(tree_path.read_text(encoding="utf-8"))["root"]["node_id"]

    first = apply_updates(target / ".context", {root_id: "Once enriched."})
    second = apply_updates(target / ".context", {root_id: "Once enriched."})

    assert first.updated == (root_id,)
    # Second pass: nothing changes because abstract + confidence already match.
    assert second.updated == ()
    assert second.unknown == ()


# ----- CLI -------------------------------------------------------------------


@pytest.mark.integration
def test_enrich_plan_cli_writes_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _ingested(tmp_path, "cli_plan")
    capsys.readouterr()  # drain ingest output

    rc = dispatch(["enrich-plan", str(target)])
    assert rc == 0
    out_path = target / ".context" / "_enrich_plan.json"
    assert out_path.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["stats"]["stub_nodes"] >= 1


@pytest.mark.integration
def test_enrich_plan_cli_errors_without_context(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bare = tmp_path / "bare"
    bare.mkdir()
    rc = dispatch(["enrich-plan", str(bare)])
    assert rc == 2
    assert "not found" in capsys.readouterr().err


@pytest.mark.integration
def test_enrich_apply_cli_round_trip(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _ingested(tmp_path, "cli_apply")
    capsys.readouterr()
    tree_path = target / ".context" / "tree.json"
    root_id = json.loads(tree_path.read_text(encoding="utf-8"))["root"]["node_id"]

    updates_file = tmp_path / "updates.json"
    updates_file.write_text(
        json.dumps({root_id: "CLI-applied abstract."}), encoding="utf-8"
    )

    rc = dispatch(
        ["enrich-apply", str(target), "--from-json", str(updates_file)]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "updated 1 abstract" in out

    after = json.loads(tree_path.read_text(encoding="utf-8"))
    assert after["root"]["abstract"] == "CLI-applied abstract."
    assert after["root"]["confidence"] == "INFERRED"


@pytest.mark.integration
def test_enrich_apply_cli_warns_on_unknown_ids(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _ingested(tmp_path, "cli_apply_unknown")
    capsys.readouterr()

    updates_file = tmp_path / "updates.json"
    updates_file.write_text(json.dumps({"bogus_id": "x"}), encoding="utf-8")

    rc = dispatch(
        ["enrich-apply", str(target), "--from-json", str(updates_file)]
    )
    assert rc == 1
    captured = capsys.readouterr()
    assert "not found in tree.json" in captured.err
    assert "bogus_id" in captured.err


@pytest.mark.integration
def test_enrich_apply_cli_requires_from_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _ingested(tmp_path, "cli_apply_missing_flag")
    capsys.readouterr()

    rc = dispatch(["enrich-apply", str(target)])
    assert rc == 2
    assert "--from-json" in capsys.readouterr().err


@pytest.mark.integration
def test_enrich_apply_cli_rejects_non_string_payload(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _ingested(tmp_path, "cli_apply_bad_payload")
    capsys.readouterr()

    updates_file = tmp_path / "updates.json"
    updates_file.write_text(json.dumps({"a": 42}), encoding="utf-8")

    rc = dispatch(
        ["enrich-apply", str(target), "--from-json", str(updates_file)]
    )
    assert rc == 2
    assert "string" in capsys.readouterr().err
