"""Docs-consistency guards for the shipped /dummyindex-update skill source.

These read the SKILL.md the installer ships and assert it does not prescribe
the destructive path or point its layer-3 verification at a file that does
not exist.
"""

from __future__ import annotations

import pytest

from tests.paths import REPO_ROOT

_UPDATE_SKILL = REPO_ROOT / "dummyindex" / "skills" / "update" / "SKILL.md"
_SKILLS_DIR = REPO_ROOT / "dummyindex" / "skills"


@pytest.mark.unit
def test_update_skill_does_not_reference_nonexistent_meta_path() -> None:
    """The real stamp is .context/meta.json; .context/cache/_meta.json never
    existed, so a `test -f` against it silently no-ops the verification."""
    for skill in _SKILLS_DIR.rglob("SKILL.md"):
        text = skill.read_text(encoding="utf-8")
        assert ".context/cache/_meta.json" not in text, skill


@pytest.mark.unit
def test_update_skill_references_real_meta_path() -> None:
    text = _UPDATE_SKILL.read_text(encoding="utf-8")
    assert ".context/meta.json" in text


@pytest.mark.unit
def test_update_skill_drops_false_non_destructive_build_all_claim() -> None:
    """The old text claimed install's `build_all(bootstrap=True)` is
    non-destructive — it isn't on a curated index. The install path is now
    preserve-only on an enriched index; the doc must reflect that."""
    text = _UPDATE_SKILL.read_text(encoding="utf-8")
    # The specific false phrasing must be gone.
    assert "build_all(bootstrap=True)" not in text
    # And the doc should describe preservation of curated content.
    assert "curated" in text.lower()
