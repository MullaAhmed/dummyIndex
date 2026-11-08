"""Unit contracts for observe keys, security scan, settings, and models."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from dummyindex.context.domains.observe.enums import (
    CorrectionStatus,
    ExposureVia,
    Verdict,
)
from dummyindex.context.domains.observe.keys import (
    evidence_key,
    evolution_enabled,
    keyed_id,
    retention_days,
)
from dummyindex.context.domains.observe.models import Attribution, Correction, Exposure
from dummyindex.context.domains.observe.security import scan_text

pytestmark = pytest.mark.unit

KEY_FILE = Path(".dummyindex") / "evidence.key"
HEX64 = re.compile(r"[0-9a-f]{64}")
KEY_A = b"A" * 32
KEY_B = b"B" * 32


def test_keyed_id_depends_on_key_and_is_stable() -> None:
    first = keyed_id("a", key=KEY_A)
    assert first != keyed_id("a", key=KEY_B)
    assert first == keyed_id("a", key=KEY_A)
    assert HEX64.fullmatch(first)


def test_evidence_key_creates_32_bytes_once(tmp_path: Path) -> None:
    key_path = tmp_path / KEY_FILE
    first = evidence_key(home=tmp_path)
    assert key_path.is_file()
    assert len(first) == 32
    assert key_path.read_bytes() == first

    mtime = key_path.stat().st_mtime_ns
    second = evidence_key(home=tmp_path)
    assert second == first
    assert key_path.read_bytes() == first
    assert key_path.stat().st_mtime_ns == mtime


def test_evidence_key_reads_existing_file(tmp_path: Path) -> None:
    key_path = tmp_path / KEY_FILE
    key_path.parent.mkdir(parents=True)
    key_path.write_bytes(KEY_A)
    assert evidence_key(home=tmp_path) == KEY_A


def test_evidence_key_rejects_wrong_length(tmp_path: Path) -> None:
    key_path = tmp_path / KEY_FILE
    key_path.parent.mkdir(parents=True)
    key_path.write_bytes(b"short")
    with pytest.raises(ValueError):
        evidence_key(home=tmp_path)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes only")
def test_evidence_key_file_mode_is_owner_only(tmp_path: Path) -> None:
    evidence_key(home=tmp_path)
    assert (tmp_path / KEY_FILE).stat().st_mode & 0o777 == 0o600


def test_evolution_enabled_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DUMMYINDEX_EVOLUTION", raising=False)
    assert evolution_enabled(home=tmp_path) is True


@pytest.mark.parametrize("value", ["0", "off", "false", "OFF"])
def test_evolution_disabled_by_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("DUMMYINDEX_EVOLUTION", value)
    assert evolution_enabled(home=tmp_path) is False


def test_evolution_disabled_when_dot_dir_is_a_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DUMMYINDEX_EVOLUTION", raising=False)
    (tmp_path / ".dummyindex").write_text("not a dir", encoding="utf-8")
    assert evolution_enabled(home=tmp_path) is False


INVISIBLE_ENDPOINTS = [
    "\u200b",
    "\u200f",
    "\u202a",
    "\u202e",
    "\u2060",
    "\u2064",
    "\u2066",
    "\u2069",
    "\ufeff",
    "\U000e0000",
    "\U000e007f",
]

INJECTION_MARKERS = [
    "Ignore previous instructions",
    "ignore all prior instructions",
    "ignore any above instructions",
    "<system>",
    "</system>",
    "<instruction>",
    "</instructions>",
    "<|im_start|>",
    "<|im_end|>",
    "<!-- dummyindex:learning -->",
]


@pytest.mark.parametrize("char", INVISIBLE_ENDPOINTS)
def test_scan_flags_invisible_unicode_endpoints(char: str) -> None:
    assert "invisible-unicode" in scan_text(f"a{char}b")


@pytest.mark.parametrize("char", ["\u2065", "\u200a"])
def test_scan_ignores_invisible_neighbours_outside_ranges(char: str) -> None:
    assert "invisible-unicode" not in scan_text(f"a{char}b")


@pytest.mark.parametrize("text", INJECTION_MARKERS)
def test_scan_flags_injection_markers(text: str) -> None:
    assert scan_text(text) == ("injection-marker",)


@pytest.mark.parametrize("text", ["<system-reminder>", "please use the other contract"])
def test_scan_allows_benign_text(text: str) -> None:
    assert scan_text(text) == ()


def test_scan_reports_both_reasons_in_fixed_order() -> None:
    assert scan_text("\u200b<system>") == ("invisible-unicode", "injection-marker")


def _settings(home: Path, text: str) -> None:
    path = home / ".claude" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_retention_defaults_without_settings(tmp_path: Path) -> None:
    assert retention_days(home=tmp_path) == 30


def test_retention_reads_cleanup_period(tmp_path: Path) -> None:
    _settings(tmp_path, json.dumps({"cleanupPeriodDays": 7}))
    assert retention_days(home=tmp_path) == 7


@pytest.mark.parametrize("value", [45, 0, -1, True, "7"])
def test_retention_falls_back_for_invalid_values(tmp_path: Path, value: object) -> None:
    _settings(tmp_path, json.dumps({"cleanupPeriodDays": value}))
    assert retention_days(home=tmp_path) == 30


def test_retention_falls_back_for_bad_json(tmp_path: Path) -> None:
    _settings(tmp_path, "{not json")
    assert retention_days(home=tmp_path) == 30


def _exposure() -> Exposure:
    return Exposure(
        item=".context/conventions/naming.md",
        version="abc",
        rules=("r1", "r2"),
        session="s" * 64,
        turn=3,
        day="2026-11-01",
        via=ExposureVia.READ,
        call="c" * 64,
        model=None,
        cli="1.0.0",
        detector=1,
    )


def _correction() -> Correction:
    return Correction(
        id="k" * 64,
        host="claude",
        session="s" * 64,
        turn=4,
        day="2026-11-02",
        source_id="src",
        byte_offset=128,
        model="m",
        cli="1.0.0",
        detector=1,
        candidates=("a.md", "b.md"),
        quarantine=("injection-marker",),
        status=CorrectionStatus.OPEN,
        ts="2026-11-02T00:00:00Z",
    )


def _attribution() -> Attribution:
    return Attribution(
        correction="k" * 64,
        verdict=Verdict.ATTRIBUTED,
        item="a.md#r1",
        durable=True,
        retracts=False,
        session="s" * 64,
        turn=4,
        day="2026-11-02",
    )


@pytest.mark.parametrize("obj", [_exposure(), _correction(), _attribution()])
def test_models_round_trip(obj: Exposure | Correction | Attribution) -> None:
    data = obj.to_dict()
    assert type(obj).from_dict(data) == obj
    assert json.loads(json.dumps(data)) == data


def test_exposure_serializes_enum_and_tuple() -> None:
    data = _exposure().to_dict()
    assert data["via"] == "read"
    assert data["rules"] == ["r1", "r2"]
    assert isinstance(data["rules"], list)


def test_correction_serializes_enum_and_tuples() -> None:
    data = _correction().to_dict()
    assert data["status"] == "open"
    assert data["candidates"] == ["a.md", "b.md"]
    assert data["quarantine"] == ["injection-marker"]


def test_attribution_serializes_enum() -> None:
    assert _attribution().to_dict()["verdict"] == "attributed"
