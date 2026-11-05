"""A session owns its edits, not accumulated drift in every discovered index."""

import json
from pathlib import Path

import pytest

from dummyindex.context import reconcile_gate as gate
from dummyindex.context.domains.memory.transcript import SessionSignal
from dummyindex.context.drift import DriftReport, DriftRow
from dummyindex.context.reconcile_scope import partition_session_drift


def _decision(monkeypatch, root: Path, reports: dict, edited=(), subagent_edits=0):
    transcript = root / "session.jsonl"
    transcript.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(gate, "discover_context_roots", lambda _: tuple(reports))
    monkeypatch.setattr(gate, "compute_drift", lambda path: reports[path])
    monkeypatch.setattr(gate, "_has_live_anchor", lambda _: False)
    monkeypatch.setattr(
        gate,
        "read_session_signal",
        lambda _: SessionSignal(
            output_tokens=50000,
            subagent_file_count=1 if subagent_edits else 0,
            main_turns=2,
            edited_paths=tuple(map(str, edited)),
            subagent_edit_count=subagent_edits,
        ),
    )
    return json.loads(
        gate.decide_block(root=root, main_transcript=transcript, stop_hook_active=False)
    )


@pytest.mark.unit
def test_only_edited_source_is_blocking_and_other_roots_are_advisory(
    monkeypatch, tmp_path: Path
) -> None:
    backend = tmp_path / "backend"
    backend.mkdir()
    reports = {
        tmp_path: DriftReport(
            rows=(DriftRow("app/x.py", "owned"), DriftRow("old.py", "old"))
        ),
        backend: DriftReport(rows=(DriftRow("api.py", "orders"),)),
    }
    result = _decision(monkeypatch, tmp_path, reports, [tmp_path / "app/x.py"])
    assert result["decision"] == "block"
    assert "owned" in result["reason"]
    assert "orders" not in result["reason"]
    assert "Unrelated context drift remains advisory" in result["reason"]


@pytest.mark.unit
def test_submodule_edits_belong_to_the_deepest_index(
    monkeypatch, tmp_path: Path
) -> None:
    backend = tmp_path / "backend"
    backend.mkdir()
    reports = {
        tmp_path: DriftReport(rows=(DriftRow("backend/api.py", "parent-copy"),)),
        backend: DriftReport(rows=(DriftRow("api.py", "orders"),)),
    }
    result = _decision(monkeypatch, tmp_path, reports, [backend / "api.py"])
    assert result["decision"] == "block"
    assert "orders" in result["reason"]
    assert "parent-copy" not in result["reason"]


@pytest.mark.unit
def test_unknown_subagent_edits_cannot_claim_every_stale_root(
    monkeypatch, tmp_path: Path
) -> None:
    result = _decision(
        monkeypatch,
        tmp_path,
        {tmp_path: DriftReport(rows=(DriftRow("old.py", "old"),))},
        subagent_edits=2,
    )
    assert "decision" not in result
    assert "advisory" in result["systemMessage"]


@pytest.mark.unit
def test_anchored_feature_signals_require_actual_path_ownership(tmp_path: Path) -> None:
    feature = tmp_path / ".context/features/owned"
    feature.mkdir(parents=True)
    (feature / "feature.json").write_text(
        json.dumps({"files": ["app/x.py"]}), encoding="utf-8"
    )
    report = DriftReport(
        rows=(), drifted_features=("owned", "unrelated"), awaiting_enrichment=("owned",)
    )
    current, rest = partition_session_drift(
        [(tmp_path, report)],
        (str(tmp_path / "app/x.py"),),
        base=tmp_path,
        context_roots=(tmp_path,),
    )
    assert current[0][1].drifted_features == ("owned",)
    assert current[0][1].awaiting_enrichment == ("owned",)
    assert rest[0][1].drifted_features == ("unrelated",)
