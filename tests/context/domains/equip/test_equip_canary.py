"""Equip invariant canary (proposal ponytail-improvements, Wave 2).

A generated item may carry ``invariants`` — load-bearing convention substrings
the tool must preserve. The canary refines the USER_MODIFIED verdict *only when
the hash differs*:

- every invariant still present in the on-disk text ⇒ ``CUSTOMIZED`` (a benign
  user edit that kept the contract);
- at least one invariant gone ⇒ ``INVARIANT_BROKEN`` (an alarm).

The CRITICAL contract (D2): both new states are *user-owned* exactly like
USER_MODIFIED — ``apply`` / ``refresh`` / ``uninstall`` leave their files
byte-untouched and never re-baseline them, so an ``INVARIANT_BROKEN`` alarm is
never laundered to PRISTINE on the next apply. With ``invariants=()`` the two
new states are unreachable, so classification + every lifecycle decision is
byte-identical to today.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.context.domains.atomic_io import write_text_atomic
from dummyindex.context.domains.equip import (
    EQUIPMENT_REL,
    EquipmentItem,
    EquipmentManifest,
    content_hash,
    read_manifest,
    write_manifest,
)
from dummyindex.context.domains.equip.enums import (
    EquipmentKind,
    EquipmentSource,
    ItemState,
)
from dummyindex.context.domains.equip.lifecycle.status import (
    classify_item,
    is_user_owned,
    refresh,
    status,
    uninstall,
)

# ----- fixtures -------------------------------------------------------------

_IMPL_REL = ".claude/agents/python-implementer.md"
# A body whose load-bearing convention lines are the two invariant substrings.
_IMPL_BODY = (
    "---\nname: python-implementer\nversion: 1.0.0\n---\n"
    "<!-- dummyindex:generated -->\n"
    "Follow @dataclass(frozen=True) for models.\n"
    "Raise EquipError, never a bare Exception.\n"
)
_INV_A = "@dataclass(frozen=True)"
_INV_B = "Raise EquipError"


def _item(
    name: str,
    rel: str,
    body: str,
    *,
    invariants: tuple[str, ...] = (),
) -> EquipmentItem:
    return EquipmentItem(
        kind=EquipmentKind.AGENT if "agents" in rel else EquipmentKind.SKILL,
        name=name,
        path=rel,
        source=EquipmentSource.GENERATED,
        capabilities=("implement",),
        version="1.0.0",
        origin_hash=content_hash(body),
        invariants=invariants,
    )


def _equipped(root: Path, *, invariants: tuple[str, ...] = ()) -> EquipmentManifest:
    """One generated, file-backed item on disk + in the manifest."""
    write_text_atomic(root / _IMPL_REL, _IMPL_BODY)
    manifest = EquipmentManifest(
        schema_version=4,
        items=(
            _item("python-implementer", _IMPL_REL, _IMPL_BODY, invariants=invariants),
        ),
    )
    write_manifest(root / ".context", manifest)
    return manifest


def _only(manifest: EquipmentManifest) -> EquipmentItem:
    return manifest.items[0]


def _cosmetic_edit(target: Path) -> None:
    """Change the hash while keeping every invariant substring intact."""
    target.write_text(
        target.read_text(encoding="utf-8") + "\n# a harmless trailing note\n",
        encoding="utf-8",
    )


def _break_invariant(target: Path) -> None:
    """Delete one invariant substring (changes the hash AND breaks the contract)."""
    text = target.read_text(encoding="utf-8").replace(_INV_B, "raise something")
    target.write_text(text, encoding="utf-8")


# ----- predicate ------------------------------------------------------------


@pytest.mark.unit
def test_is_user_owned_covers_all_three_states() -> None:
    assert is_user_owned(ItemState.USER_MODIFIED) is True
    assert is_user_owned(ItemState.CUSTOMIZED) is True
    assert is_user_owned(ItemState.INVARIANT_BROKEN) is True
    # PRISTINE / MISSING / ADOPTED are NOT user-owned — they must stay editable.
    assert is_user_owned(ItemState.PRISTINE) is False
    assert is_user_owned(ItemState.MISSING) is False
    assert is_user_owned(ItemState.ADOPTED) is False


# ----- classify_item: empty-invariants backward compatibility ---------------


@pytest.mark.integration
def test_empty_invariants_classifies_exactly_as_today(tmp_path: Path) -> None:
    """With no invariants the two new states are UNREACHABLE — a hash mismatch
    is plain USER_MODIFIED, byte-identical to today."""
    root = tmp_path
    manifest = _equipped(root)  # no invariants
    item = _only(manifest)
    assert classify_item(root, item) is ItemState.PRISTINE

    _cosmetic_edit(root / _IMPL_REL)
    assert classify_item(root, item) is ItemState.USER_MODIFIED

    (root / _IMPL_REL).unlink()
    assert classify_item(root, item) is ItemState.MISSING


# ----- classify_item: with invariants ---------------------------------------


@pytest.mark.integration
def test_cosmetic_edit_with_invariants_is_customized(tmp_path: Path) -> None:
    root = tmp_path
    manifest = _equipped(root, invariants=(_INV_A, _INV_B))
    item = _only(manifest)
    _cosmetic_edit(root / _IMPL_REL)
    assert classify_item(root, item) is ItemState.CUSTOMIZED


@pytest.mark.integration
def test_deleting_an_invariant_is_invariant_broken(tmp_path: Path) -> None:
    root = tmp_path
    manifest = _equipped(root, invariants=(_INV_A, _INV_B))
    item = _only(manifest)
    _break_invariant(root / _IMPL_REL)
    assert classify_item(root, item) is ItemState.INVARIANT_BROKEN


@pytest.mark.integration
def test_pristine_with_invariants_stays_pristine(tmp_path: Path) -> None:
    """Invariants are consulted ONLY when the hash differs — an untouched file
    is still PRISTINE even though it carries invariants."""
    root = tmp_path
    manifest = _equipped(root, invariants=(_INV_A, _INV_B))
    assert classify_item(root, _only(manifest)) is ItemState.PRISTINE


# ----- status surfaces the new states ---------------------------------------


@pytest.mark.integration
def test_status_reports_customized_and_invariant_broken(tmp_path: Path) -> None:
    root = tmp_path
    manifest = _equipped(root, invariants=(_INV_A, _INV_B))
    _break_invariant(root / _IMPL_REL)
    report = status(root, manifest)
    states = {name: state for name, state, _v in report.items}
    assert states["python-implementer"] is ItemState.INVARIANT_BROKEN


# ----- never-clobber: refresh -----------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize("mutate", [_cosmetic_edit, _break_invariant])
def test_refresh_never_clobbers_user_owned_invariant_states(
    tmp_path: Path, mutate
) -> None:
    root = tmp_path
    manifest = _equipped(root, invariants=(_INV_A, _INV_B))
    target = root / _IMPL_REL
    mutate(target)
    before = target.read_text(encoding="utf-8")
    before_hash = _only(manifest).origin_hash

    # Offer a genuinely different fresh render — a PRISTINE item would be rewritten.
    report = refresh(root, fresh_renders={"python-implementer": _IMPL_BODY + "\nNEW\n"})

    assert "python-implementer" in report.skipped_user_modified
    assert "python-implementer" not in report.refreshed
    # byte-for-byte survival
    assert target.read_text(encoding="utf-8") == before
    # NOT re-baselined: the persisted origin_hash is unchanged
    after = read_manifest(root / ".context")
    assert after.items[0].origin_hash == before_hash


@pytest.mark.integration
def test_refresh_reports_alarm_for_invariant_broken(tmp_path: Path) -> None:
    root = tmp_path
    _equipped(root, invariants=(_INV_A, _INV_B))
    _break_invariant(root / _IMPL_REL)
    report = refresh(root, fresh_renders={"python-implementer": _IMPL_BODY})
    assert report.alarm_invariant_broken == ("python-implementer",)


@pytest.mark.integration
def test_refresh_customized_not_in_alarm(tmp_path: Path) -> None:
    """A cosmetic CUSTOMIZED edit is user-owned but NOT an alarm."""
    root = tmp_path
    _equipped(root, invariants=(_INV_A, _INV_B))
    _cosmetic_edit(root / _IMPL_REL)
    report = refresh(root, fresh_renders={"python-implementer": _IMPL_BODY})
    assert report.alarm_invariant_broken == ()
    assert "python-implementer" in report.skipped_user_modified


@pytest.mark.integration
def test_refresh_empty_invariants_alarm_is_empty(tmp_path: Path) -> None:
    """Backward-compat: with no invariants the alarm tuple is always empty."""
    root = tmp_path
    _equipped(root)  # no invariants
    _cosmetic_edit(root / _IMPL_REL)
    report = refresh(root, fresh_renders={"python-implementer": _IMPL_BODY + "\nNEW\n"})
    assert report.alarm_invariant_broken == ()
    assert "python-implementer" in report.skipped_user_modified


# ----- alarm is surfaced to the user (not just stored) ----------------------


@pytest.mark.unit
def test_refresh_renderer_surfaces_invariant_broken_alarm(capsys) -> None:
    """`equip refresh` must RENDER the alarm, not just compute it — else the
    canary's whole point (a visible alarm) is lost in the user-modified list."""
    from dummyindex.cli.equip.verbs import _print_refresh_report
    from dummyindex.context.domains.equip.lifecycle.status import RefreshReport

    report = RefreshReport(
        skipped_user_modified=("python-implementer",),
        alarm_invariant_broken=("python-implementer",),
    )
    _print_refresh_report(report, dry_run=False)
    out = capsys.readouterr().out
    assert "INVARIANT_BROKEN" in out
    assert "broken" in out
    assert "python-implementer" in out


@pytest.mark.unit
def test_refresh_renderer_silent_alarm_when_clean(capsys) -> None:
    """No alarm section when nothing is INVARIANT_BROKEN (back-compat output)."""
    from dummyindex.cli.equip.verbs import _print_refresh_report
    from dummyindex.context.domains.equip.lifecycle.status import RefreshReport

    _print_refresh_report(RefreshReport(refreshed=("x",)), dry_run=False)
    out = capsys.readouterr().out
    assert "INVARIANT_BROKEN" not in out
    assert "⚠" not in out


# ----- never-clobber: uninstall ---------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize("mutate", [_cosmetic_edit, _break_invariant])
def test_uninstall_keeps_user_owned_invariant_states(tmp_path: Path, mutate) -> None:
    root = tmp_path
    manifest = _equipped(root, invariants=(_INV_A, _INV_B))
    target = root / _IMPL_REL
    mutate(target)
    before = target.read_text(encoding="utf-8")

    report = uninstall(root, manifest)

    assert target.exists()
    assert target.read_text(encoding="utf-8") == before  # byte-for-byte
    assert "python-implementer" in report.skipped_user_modified
    assert "python-implementer" not in report.removed


# ----- never-clobber across the CLI apply write path ------------------------


def _project(tmp_path: Path) -> Path:
    """A minimal indexed python repo so `equip apply` can render."""
    context_dir = tmp_path / ".context"
    (context_dir / "map").mkdir(parents=True, exist_ok=True)
    (context_dir / "map" / "files.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "files": [
                    {"path": "src/f0.py", "language": "python", "size_bytes": 10}
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (context_dir / "conventions").mkdir(parents=True, exist_ok=True)
    (context_dir / "conventions" / "naming.md").write_text(
        "# naming\n", encoding="utf-8"
    )
    return tmp_path


def _inject_invariants(root: Path, name: str, invariants: list[str]) -> str:
    """Stamp ``invariants`` onto a generated record and return its on-disk path."""
    data = json.loads((root / ".context" / EQUIPMENT_REL).read_text(encoding="utf-8"))
    rel = ""
    for entry in data["items"]:
        if entry["name"] == name:
            entry["invariants"] = invariants
            rel = entry["path"]
    (root / ".context" / EQUIPMENT_REL).write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )
    assert rel, f"no generated item named {name!r}"
    return rel


def _origin_hash(root: Path, name: str) -> str | None:
    data = json.loads((root / ".context" / EQUIPMENT_REL).read_text(encoding="utf-8"))
    return next(i["origin_hash"] for i in data["items"] if i["name"] == name)


@pytest.mark.integration
def test_apply_does_not_clobber_or_rebaseline_customized(tmp_path: Path) -> None:
    from dummyindex.cli.equip import run as run_equip

    root = _project(tmp_path)
    assert run_equip(["apply", str(root)]) == 0
    # An invariant substring that genuinely appears in the rendered body.
    target_rel = _inject_invariants(
        root, "python-implementer", ["Immutable/additive by default."]
    )
    target = root / target_rel
    # cosmetic edit that keeps the invariant substring → CUSTOMIZED
    target.write_text(
        target.read_text(encoding="utf-8") + "\n# cosmetic\n", encoding="utf-8"
    )
    before = target.read_text(encoding="utf-8")
    before_hash = _origin_hash(root, "python-implementer")

    assert run_equip(["apply", str(root)]) == 0

    assert target.read_text(encoding="utf-8") == before  # byte-untouched
    assert _origin_hash(root, "python-implementer") == before_hash  # not re-baselined


@pytest.mark.integration
def test_apply_does_not_launder_invariant_broken_to_pristine(tmp_path: Path) -> None:
    from dummyindex.cli.equip import run as run_equip
    from dummyindex.context.domains.equip import read_manifest as _read

    root = _project(tmp_path)
    assert run_equip(["apply", str(root)]) == 0
    invariant = "Immutable/additive by default."
    target_rel = _inject_invariants(root, "python-implementer", [invariant])
    target = root / target_rel
    # delete the invariant substring → INVARIANT_BROKEN
    text = target.read_text(encoding="utf-8").replace(invariant, "mutate freely.")
    assert text != target.read_text(
        encoding="utf-8"
    )  # the substring really was present
    target.write_text(text, encoding="utf-8")
    before = target.read_text(encoding="utf-8")

    # A second apply must NOT rewrite the file or re-baseline the record.
    assert run_equip(["apply", str(root)]) == 0
    assert target.read_text(encoding="utf-8") == before

    # And classification STILL reports INVARIANT_BROKEN — no laundering to PRISTINE.
    manifest = _read(root / ".context")
    item = next(i for i in manifest.items if i.name == "python-implementer")
    assert classify_item(root, item) is ItemState.INVARIANT_BROKEN
