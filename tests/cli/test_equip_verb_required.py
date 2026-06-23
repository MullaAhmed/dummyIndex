"""`equip` is verb-required — a bare probe must never mutate the repo.

Before this guard, ``_split_verb`` defaulted to ``EquipVerb.APPLY`` whenever
the first token was not a verb, so bare ``equip`` (a help/discovery probe) ran
a full apply: it wrote ``.claude/agents/*`` + ``.claude/skills/*`` and created
``.context/equipment.json`` from nothing. Now the verbless form prints usage
and exits 2 (the read-only ``--dry-run`` carve-out is kept), and an explicit
``equip apply`` is required to mutate — and refuses on an un-indexed repo.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.cli.equip import run as equip_run


def _wrote_anything(root: Path) -> bool:
    return (root / ".claude").exists() or (
        root / ".context" / "equipment.json"
    ).exists()


@pytest.mark.unit
def test_bare_equip_is_usage_not_apply(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Bare ``equip`` prints usage, exits 2, writes nothing."""
    code = equip_run(["--root", str(tmp_path)])
    err = capsys.readouterr().err
    assert code == 2, "bare equip must not apply (exit 2)"
    assert "equip" in err
    assert "apply" in err, "usage must point at the explicit `equip apply` verb"
    assert not _wrote_anything(tmp_path), "bare equip mutated the repo"


@pytest.mark.unit
def test_equip_unknown_positional_is_usage_not_apply(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A bare path (the old ``equip <path>`` form) no longer auto-applies."""
    (tmp_path / "src").mkdir()
    code = equip_run([str(tmp_path / "src"), "--root", str(tmp_path)])
    assert code == 2
    assert not _wrote_anything(tmp_path)


@pytest.mark.unit
def test_equip_dry_run_carveout_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verbless ``equip --dry-run`` stays allowed — it is read-only."""
    code = equip_run(["--dry-run", "--root", str(tmp_path)])
    assert code == 0
    assert not _wrote_anything(tmp_path)


@pytest.mark.unit
def test_equip_apply_refuses_without_context(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Explicit ``equip apply`` on an un-indexed repo refuses (exit 1), no write."""
    code = equip_run(["apply", "--root", str(tmp_path)])
    err = capsys.readouterr().err
    assert code == 1, "apply without .context/ must refuse"
    assert "ingest" in err or ".context" in err
    assert not _wrote_anything(tmp_path)


@pytest.mark.unit
def test_equip_apply_writes_with_context(tmp_path: Path) -> None:
    """Explicit ``equip apply`` on an indexed repo applies."""
    (tmp_path / ".context").mkdir()
    code = equip_run(["apply", "--root", str(tmp_path)])
    assert code == 0
    assert (tmp_path / ".context" / "equipment.json").exists()
