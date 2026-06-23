"""The renderer populates a specialist's ``invariants`` as manifest metadata.

Wave 3, task 13 of the *ponytail-improvements* proposal — the piece that makes
the Wave-2 invariant canary *real* (without it the canary is a no-op): when a
generated specialist's :class:`EquipmentItem` is assembled, ``invariants`` is
set to a few load-bearing convention substrings that are GUARANTEED to appear
verbatim in that specialist's rendered body.

Two contracts are proven here:

- ``invariants`` is **manifest metadata only** (D4) — assembled the same way
  ``grounding_docs`` → ``grounded_in`` is, and **never** injected into the
  rendered bytes, so adding it cannot shift the ``origin_hash`` baseline.
- the canary round-trip works end to end: render → write to disk → delete ONE
  invariant substring → :func:`classify_item` reports ``INVARIANT_BROKEN``; a
  cosmetic edit that keeps every invariant reports ``CUSTOMIZED``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.context.domains.equip import render_generated_set
from dummyindex.context.domains.equip.enums import ItemState
from dummyindex.context.domains.equip.generate.specialists import (
    SPECIALIST_TEMPLATES,
    invariants_for,
    specialist_spec,
)
from dummyindex.context.domains.equip.lifecycle.hashing import content_hash
from dummyindex.context.domains.equip.lifecycle.status import classify_item
from dummyindex.context.domains.equip.models import EquipmentItem, StackProfile


def _profile() -> StackProfile:
    return StackProfile(label="python", frameworks=("FastAPI",))


def _render_specialist(capability: str) -> tuple[EquipmentItem, str]:
    """Render one specialist; return its ``(item, content)``."""
    spec = specialist_spec(capability, label="python", proj="backend")
    rendered = render_generated_set(
        profile=_profile(),
        specs=(spec,),
        conventions=(".context/conventions/naming.md",),
        grounding=(".context/HOW_TO_USE.md", ".context/conventions/naming.md"),
        proj="backend",
    )
    item, _rel, content = rendered[0]
    return item, content


# ----- invariants are populated + verbatim in the rendered body --------------


@pytest.mark.unit
@pytest.mark.parametrize("capability", sorted(SPECIALIST_TEMPLATES))
def test_rendered_specialist_has_nonempty_invariants(capability: str) -> None:
    item, _content = _render_specialist(capability)
    assert item.invariants, f"{capability} specialist carries no invariants"
    # A small, curated set (2–3) — load-bearing, not the whole body.
    assert 2 <= len(item.invariants) <= 3


@pytest.mark.unit
@pytest.mark.parametrize("capability", sorted(SPECIALIST_TEMPLATES))
def test_every_invariant_is_a_literal_substring_of_the_rendered_body(
    capability: str,
) -> None:
    # The canary only works if each invariant is GUARANTEED present in a pristine
    # render — so a pristine body must contain every one of them verbatim.
    item, content = _render_specialist(capability)
    for inv in item.invariants:
        assert inv in content, (
            f"{capability}: invariant {inv!r} is not a literal substring of the "
            "rendered body — the canary would mis-fire on a pristine file"
        )


@pytest.mark.unit
@pytest.mark.parametrize("capability", sorted(SPECIALIST_TEMPLATES))
def test_invariants_carry_no_template_slot(capability: str) -> None:
    # A substring containing a ``{{slot}}`` is not GUARANTEED verbatim (it varies
    # per repo) — every chosen invariant must be slot-free.
    for inv in invariants_for((capability,)):
        assert "{{" not in inv and "}}" not in inv


# ----- invariants are metadata-only: origin_hash is unchanged ----------------


@pytest.mark.unit
@pytest.mark.parametrize("capability", sorted(SPECIALIST_TEMPLATES))
def test_invariants_do_not_perturb_origin_hash(capability: str) -> None:
    # D4: invariants live only in the manifest entry — the origin_hash is the
    # sha256 of the rendered bytes, which must equal the hash of the content the
    # renderer produced (invariants never entered those bytes).
    item, content = _render_specialist(capability)
    assert item.origin_hash == content_hash(content)
    # And none of the invariant strings were smuggled into the manifest's hashed
    # surface: the recorded hash matches the body alone, byte-for-byte.
    assert item.origin_hash and item.origin_hash.startswith("sha256:")


@pytest.mark.unit
def test_core_four_carry_no_invariants() -> None:
    # Invariants back a *specialist's* convention contract; the core four are
    # exercised by the Wave-2 canary tests directly. A spec with no registered
    # invariants (the core four have none here) must stay empty — back-compat,
    # and so to_dict omits the key (a v3 manifest stays byte-identical, D3).
    assert invariants_for(("implement",)) == ()
    assert invariants_for(("test",)) == ()


# ----- the canary round-trip (the proof it is not a no-op) -------------------


@pytest.mark.integration
def test_delete_one_invariant_round_trips_to_invariant_broken(
    tmp_path: Path,
) -> None:
    """Render → write → delete ONE invariant substring → INVARIANT_BROKEN."""
    item, content = _render_specialist("database")
    target = tmp_path / item.path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    # A pristine on-disk file classifies PRISTINE (the canary stays dormant).
    assert classify_item(tmp_path, item) is ItemState.PRISTINE

    # Delete exactly one invariant substring — the file is now both hash-changed
    # AND missing a load-bearing convention → INVARIANT_BROKEN.
    victim = item.invariants[0]
    assert victim in content  # guard: it really was present in the pristine body
    target.write_text(content.replace(victim, "(removed)"), encoding="utf-8")
    assert classify_item(tmp_path, item) is ItemState.INVARIANT_BROKEN


@pytest.mark.integration
def test_cosmetic_edit_keeping_invariants_round_trips_to_customized(
    tmp_path: Path,
) -> None:
    """Render → write → cosmetic edit that keeps every invariant → CUSTOMIZED."""
    item, content = _render_specialist("database")
    target = tmp_path / item.path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    # Append a harmless note: the hash changes but every invariant survives.
    target.write_text(content + "\n<!-- my own note -->\n", encoding="utf-8")
    for inv in item.invariants:
        assert inv in target.read_text(encoding="utf-8")
    assert classify_item(tmp_path, item) is ItemState.CUSTOMIZED
