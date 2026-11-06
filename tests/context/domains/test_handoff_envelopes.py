import json

import pytest

from dummyindex.context.domains.buildloop.envelopes import envelope, task_binding


def test_handoff_preserves_selected_policy_identity(tmp_path):
    context = tmp_path / ".context"
    proposal = context / "proposals/task"
    proposal.mkdir(parents=True)
    (tmp_path / "policy.md").write_text("Use the smallest complete change.")
    (proposal / "proposal.json").write_text(
        json.dumps({"policies": [{"name": "ponytail", "path": "policy.md"}]})
    )
    entry = {"task_id": "task-42", "text": "Repair source", "role_path": None}
    first = task_binding(entry, context, proposal)
    assert first["bindings"]["policies"][0]["name"] == "ponytail"
    (tmp_path / "policy.md").write_text("Changed policy")
    second = task_binding(entry, context, proposal)
    assert first["bindings"]["policies"] != second["bindings"]["policies"]
    assert first["task_id"] == second["task_id"]


def test_large_logs_and_unproven_completion_are_rejected():
    with pytest.raises(ValueError, match="artifact"):
        envelope("t", state="running", next_action="x" * 9000)
    with pytest.raises(ValueError, match="evidence"):
        envelope("t", state="verified")
