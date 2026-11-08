"""`context features-list` domain: INDEX.json reading and schema_version gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.context.domains.features_list import (
    FeaturesListError,
    list_features,
)
from tests.paths import FIXTURES_DIR

FIXTURE_ROOT = FIXTURES_DIR / "features-list"


def _write_index(root: Path, payload: object) -> None:
    features_dir = root / ".context" / "features"
    features_dir.mkdir(parents=True, exist_ok=True)
    (features_dir / "INDEX.json").write_text(json.dumps(payload), encoding="utf-8")


def _entry(**overrides: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "feature_id": "build-loop",
        "kind": "community",
        "name": "Build loop",
        "summary": "Runs the build.",
        "member_count": 3,
        "file_count": 2,
        "entry_point_count": 1,
        "flow_count": 0,
        "confidence": "EXTRACTED",
        "path": "features/build-loop/",
    }
    entry.update(overrides)
    return entry


@pytest.mark.unit
def test_real_index_shape_is_returned_in_order(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / ".context").mkdir(parents=True)
    (root / ".context" / "features").mkdir()
    fixture = FIXTURE_ROOT / ".context" / "features" / "INDEX.json"
    (root / ".context" / "features" / "INDEX.json").write_bytes(fixture.read_bytes())

    payload = list_features(root)
    assert payload["schema_version"] == 1
    assert Path(payload["root"]).is_absolute()
    assert payload["skipped"] == 0
    assert [f["feature_id"] for f in payload["features"]] == [
        "agent-instructions",
        "audit-panel",
        "behavior-gate",
    ]
    first = payload["features"][0]
    assert first["name"] == "Agent-facing instruction docs"
    assert first["member_count"] == 79
    assert first["confidence"] == "INFERRED"


@pytest.mark.unit
@pytest.mark.parametrize("version", [2, 0, "1", True, None])
def test_schema_version_other_than_integer_one_is_refused(
    tmp_path: Path, version: object
) -> None:
    payload: dict[str, object] = {"features": [_entry()]}
    if version is not None:
        payload["schema_version"] = version
    _write_index(tmp_path, payload)
    with pytest.raises(FeaturesListError) as info:
        list_features(tmp_path)
    assert info.value.code == "unsupported_schema_version"


@pytest.mark.unit
def test_missing_context_is_not_indexed(tmp_path: Path) -> None:
    with pytest.raises(FeaturesListError) as info:
        list_features(tmp_path)
    assert info.value.code == "not_indexed"


@pytest.mark.unit
def test_context_without_features_index_is_not_indexed(tmp_path: Path) -> None:
    (tmp_path / ".context").mkdir()
    with pytest.raises(FeaturesListError) as info:
        list_features(tmp_path)
    assert info.value.code == "not_indexed"


@pytest.mark.unit
def test_unreadable_json_is_invalid_index(tmp_path: Path) -> None:
    features_dir = tmp_path / ".context" / "features"
    features_dir.mkdir(parents=True)
    (features_dir / "INDEX.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(FeaturesListError) as info:
        list_features(tmp_path)
    assert info.value.code == "invalid_index"


@pytest.mark.unit
def test_items_breaking_the_minimum_shape_are_skipped_and_counted(
    tmp_path: Path,
) -> None:
    _write_index(
        tmp_path,
        {
            "schema_version": 1,
            "features": [
                _entry(),
                _entry(feature_id="Bad_ID"),
                _entry(feature_id="no-confidence", confidence="MAYBE"),
                _entry(feature_id="bool-count", member_count=True),
                _entry(feature_id="no-name", name=""),
                "not an object",
            ],
        },
    )
    payload = list_features(tmp_path)
    assert [f["feature_id"] for f in payload["features"]] == ["build-loop"]
    assert payload["skipped"] == 5


@pytest.mark.unit
def test_optional_fields_are_dropped_when_wrong_type(tmp_path: Path) -> None:
    _write_index(
        tmp_path,
        {"schema_version": 1, "features": [_entry(summary=None, file_count="2")]},
    )
    (item,) = list_features(tmp_path)["features"]
    assert item["summary"] == ""
    assert "file_count" not in item
