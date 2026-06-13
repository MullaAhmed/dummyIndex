"""Repo/packaging hygiene guards for the dummyindex source checkout.

Two classes of rot these tests turn from silent into red:

1. Stale local packaging dirs (``dummyindex.egg-info/``, ``build/``) left by
   an old ``pip install .`` — ``importlib.metadata`` resolves the repo-root
   egg-info first under ``python3 -m``, so ``dummyindex --version`` (and every
   installed __VERSION__ stamp) reports the *old* version.
2. Realistic secret-shaped placeholders sneaking into shipped skill prompts —
   consumer repos run secret scanners over committed ``.context``/skill docs,
   so shipped markdown must only ever use obviously-fake placeholders
   (``<API_KEY>``, ``YOUR-TOKEN-HERE``), never ``ghp_…`` / ``sk-…`` / ``AKIA…``
   shapes.
"""
from __future__ import annotations

import re

import pytest

from tests.paths import REPO_ROOT

_IS_SOURCE_CHECKOUT = (REPO_ROOT / "pyproject.toml").is_file() and (
    REPO_ROOT / ".git"
).exists()

_STALE_PACKAGING_DIRS = ("dummyindex.egg-info", "build")

# Realistic credential shapes that trip secret scanners (detect-secrets,
# gitleaks). Word-bounded + length-gated so prose like "task-dependent"
# can't match.
_SECRET_SHAPES = re.compile(
    r"\b(?:ghp_[A-Za-z0-9]{16,}|sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{12,})"
)


@pytest.mark.unit
@pytest.mark.skipif(not _IS_SOURCE_CHECKOUT, reason="not a git source checkout")
def test_no_stale_local_packaging_dirs() -> None:
    stale = [d for d in _STALE_PACKAGING_DIRS if (REPO_ROOT / d).exists()]
    assert not stale, (
        f"stale local packaging artefacts {stale} shadow the real package "
        "version: importlib.metadata finds the repo-root egg-info first, so "
        "`python3 -m dummyindex --version` (and every installed __VERSION__ "
        "stamp) reports the old version, and a stale build/lib re-bundles "
        "deleted modules into the next wheel. Fix: "
        "`rm -rf dummyindex.egg-info build`."
    )


@pytest.mark.unit
def test_shipped_skill_markdown_has_no_realistic_secret_shapes() -> None:
    skills_dir = REPO_ROOT / "dummyindex" / "skills"
    offenders: list[str] = []
    for md in sorted(skills_dir.rglob("*.md*")):
        if not md.is_file():
            continue
        match = _SECRET_SHAPES.search(md.read_text(encoding="utf-8"))
        if match:
            offenders.append(f"{md.relative_to(REPO_ROOT)}: {match.group(0)[:12]}…")
    assert not offenders, (
        "shipped skill markdown contains realistic secret-shaped strings "
        f"(consumer secret scanners will fail CI on them): {offenders}"
    )
