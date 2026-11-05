"""Checklist identity must survive reordering and never guess ambiguous labels."""

import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from dummyindex.context.domains.buildloop import (
    BuildLoopError,
    flip_item,
    parse_checklist,
    skip_item,
)
from dummyindex.context.domains.buildloop.receipts import check_with_receipt


@pytest.mark.unit
def test_stable_id_selects_same_task_after_reordering_and_skip(tmp_path: Path) -> None:
    path = tmp_path / "checklist.md"
    path.write_text("- [ ] Build parser\n- [ ] Test parser\n", encoding="utf-8")
    task = parse_checklist(path)[0]
    path.write_text("- [ ] Test parser\n- [ ] Build parser\n", encoding="utf-8")
    assert flip_item(path, task.item_id).text == "Build parser"
    other = parse_checklist(path)[0]
    skip_item(path, other.item_id, "Already covered")
    assert parse_checklist(path)[0].item_id == other.item_id


@pytest.mark.unit
def test_explicit_id_survives_text_changes_and_preserves_via(tmp_path: Path) -> None:
    path = tmp_path / "checklist.md"
    path.write_text(
        "- [ ] Build parser — via ponytail <!-- task:parser -->\n", encoding="utf-8"
    )
    assert parse_checklist(path)[0].via == "ponytail"
    path.write_text(
        "- [ ] Build improved parser — via ponytail <!-- task:parser -->\n",
        encoding="utf-8",
    )
    assert flip_item(path, "parser").item_id == "parser"


@pytest.mark.unit
def test_numeric_label_and_position_conflict_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "checklist.md"
    path.write_text("- [ ] 1. Build parser\n- [ ] 2. Test parser\n", encoding="utf-8")
    with pytest.raises(BuildLoopError, match="ambiguous numeric"):
        flip_item(path, "1")
    assert not any(i.done for i in parse_checklist(path))
    assert flip_item(path, "index:1").text == "2. Test parser"


@pytest.mark.unit
def test_duplicate_ids_and_empty_selectors_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "checklist.md"
    path.write_text("- [ ] Repeat\n- [ ] Repeat\n", encoding="utf-8")
    key = parse_checklist(path)[0].item_id
    with pytest.raises(BuildLoopError, match="ambiguous task ID"):
        flip_item(path, key)
    with pytest.raises(BuildLoopError, match="must not be empty"):
        flip_item(path, "")


@pytest.mark.unit
def test_receipt_rejects_changed_artifacts_and_preserves_task_identity(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "dummyindex.context.domains.buildloop.receipts.head_commit",
        lambda _root: "revision",
    )
    checklist = tmp_path / ".context/proposals/work/checklist.md"
    checklist.parent.mkdir(parents=True)
    checklist.write_text("- [ ] Build parser\n", encoding="utf-8")
    item = parse_checklist(checklist)[0]
    artifact = tmp_path / "parser.py"
    artifact.write_text("correct\n", encoding="utf-8")
    evidence = tmp_path / "verification.txt"
    evidence.write_text("targeted regression passed\n", encoding="utf-8")
    receipt = {
        "task_id": item.item_id,
        "item_sha256": hashlib.sha256(item.text.encode()).hexdigest(),
        "source_commit": "revision",
        "state": "verified",
        "artifacts": [
            {
                "path": "parser.py",
                "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            }
        ],
        "evidence": [
            {
                "path": "verification.txt",
                "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
            }
        ],
    }
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    artifact.write_text("changed\n", encoding="utf-8")
    with pytest.raises(BuildLoopError, match="changed"):
        check_with_receipt(checklist, item.item_id, path)
    assert not parse_checklist(checklist)[0].done
    artifact.write_text("correct\n", encoding="utf-8")
    assert check_with_receipt(checklist, item.item_id, path).done
    assert (
        json.loads((checklist.parent / "checks.json").read_text())[item.item_id][
            "state"
        ]
        == "verified"
    )
    assert (
        json.loads((checklist.parent / "checks.json").read_text())[item.item_id][
            "task_id"
        ]
        == item.item_id
    )
    receipt["item_id"] = "another-task"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(BuildLoopError, match="conflicting task_id"):
        check_with_receipt(checklist, item.item_id, path)


def _parallel_receipts(tmp_path: Path, monkeypatch) -> tuple[Path, list[Path]]:
    monkeypatch.setattr(
        "dummyindex.context.domains.buildloop.receipts.head_commit",
        lambda _root: "revision",
    )
    checklist = tmp_path / ".context/proposals/work/checklist.md"
    checklist.parent.mkdir(parents=True)
    checklist.write_text("- [ ] Build parser\n- [ ] Build lexer\n", encoding="utf-8")
    artifact = tmp_path / "parser.py"
    artifact.write_text("correct\n", encoding="utf-8")
    receipts = []
    for index, item in enumerate(parse_checklist(checklist)):
        path = tmp_path / f"receipt-{index}.json"
        path.write_text(
            json.dumps(
                {
                    "task_id": item.item_id,
                    "task_sha256": hashlib.sha256(item.text.encode()).hexdigest(),
                    "source_commit": "revision",
                    "state": "implemented",
                    "artifacts": [
                        {
                            "path": artifact.name,
                            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        receipts.append(path)
    return checklist, receipts


@pytest.mark.unit
def test_parallel_receipts_preserve_both_records_and_checkboxes(
    tmp_path: Path, monkeypatch
) -> None:
    import dummyindex.context.domains.buildloop.receipts as module

    checklist, receipts = _parallel_receipts(tmp_path, monkeypatch)
    items = parse_checklist(checklist)
    original = module.write_text_atomic

    def delayed_write(path, text):
        # Without the lock both writers have read the old map before publishing.
        time.sleep(0.1)
        return original(path, text)

    monkeypatch.setattr(module, "write_text_atomic", delayed_write)
    start = threading.Barrier(2)

    def complete(index):
        start.wait(timeout=5)
        return check_with_receipt(checklist, items[index].item_id, receipts[index])

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(item.done for item in pool.map(complete, (0, 1)))
    assert all(item.done for item in parse_checklist(checklist))
    stored = json.loads((checklist.parent / "checks.json").read_text())
    assert set(stored) == {item.item_id for item in items}


@pytest.mark.unit
@pytest.mark.parametrize("plain_operation", ["check", "skip"])
def test_plain_checklist_mutations_share_the_receipt_lock(
    tmp_path: Path, monkeypatch, plain_operation: str
) -> None:
    checklist, receipts = _parallel_receipts(tmp_path, monkeypatch)
    items = parse_checklist(checklist)
    original = Path.read_text

    def delayed_read(path, *args, **kwargs):
        text = original(path, *args, **kwargs)
        if path == checklist:
            time.sleep(0.05)
        return text

    monkeypatch.setattr(Path, "read_text", delayed_read)
    start = threading.Barrier(2)

    def complete(index):
        start.wait(timeout=5)
        if index == 0:
            return check_with_receipt(checklist, items[0].item_id, receipts[0])
        if plain_operation == "skip":
            return skip_item(checklist, items[1].item_id, "Already covered")
        return flip_item(checklist, items[1].item_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(item.done for item in pool.map(complete, (0, 1)))
    assert all(item.done for item in parse_checklist(checklist))
    assert set(json.loads((checklist.parent / "checks.json").read_text())) == {
        items[0].item_id
    }
