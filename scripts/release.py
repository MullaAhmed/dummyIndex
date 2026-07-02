#!/usr/bin/env python3
"""Minimal conventional-commit release driver — replaces release-please.

On a push to ``main`` the workflow runs this. It reads the commits since the
last ``vX.Y.Z`` tag, decides the version bump from their conventional-commit
types, and (when a release is warranted) bumps ``pyproject.toml``, prepends
``CHANGELOG.md``, and emits ``released`` / ``version`` plus a notes file. The
*side effects that touch git history* — the commit, the push, and the GitHub
Release — live in the workflow, not here, so this module stays pure and
unit-tested and the irreversible steps are visible in one place.

Version policy (mirrors the old ``release-please-config.json``, pre-1.0):
  "release" in a commit/PR name -> minor  (explicit release, even with no feat/fix)
  feat / BREAKING  -> minor   (breaking stays in 0.x: bump-minor-pre-major)
  fix              -> patch
  perf/refactor/docs/chore/ci/test alone -> no release

A commit subject (or merged-PR title) that names a release as a whole word —
e.g. ``release: 0.31.0``, ``chore(release): …``, a merged ``release-0.31.0``
branch — forces the full minor bump (0.30.0 -> 0.31.0) regardless of the other
commit types, so a release PR carrying no feat/fix still cuts a release. This
runs only on pushes to ``main`` (the workflow trigger is unchanged).

The decision functions take plain data so they can be tested without git.
"""

from __future__ import annotations

import os
import re
import subprocess
from datetime import date
from pathlib import Path

# `type(scope)!:` — the conventional-commit header. `bang` (`!`) and a
# `BREAKING CHANGE:` body trailer both mark a breaking change.
_HEADER = re.compile(r"^(?P<type>\w+)(?P<scope>\([^)]*\))?(?P<bang>!)?:")

# An explicit release signal: any commit subject or merged-PR title that names
# a release as a whole word — `release: 0.31.0`, `chore(release): …`, a merged
# `release-0.31.0` branch, `Release 0.31.0`. Such a subject forces a full
# (minor, pre-1.0) release even when no feat/fix is present. Whole-word only,
# so `released` / `prerelease` in ordinary prose don't trip it.
_RELEASE_SIGNAL = re.compile(r"\brelease\b", re.IGNORECASE)

# Changelog sections, in render order — the visible subset of the old
# release-please `changelog-sections` (test/chore/ci were `hidden`).
_SECTIONS: tuple[tuple[str, str], ...] = (
    ("feat", "Added"),
    ("fix", "Fixed"),
    ("perf", "Performance"),
    ("refactor", "Changed"),
    ("docs", "Documentation"),
)

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
CHANGELOG = ROOT / "CHANGELOG.md"
NOTES_FILE = ROOT / "release-notes.md"


def commit_type(subject: str) -> tuple[str | None, bool]:
    """``(type, is_breaking)`` for a commit subject. ``(None, False)`` when the
    subject isn't a conventional-commit header."""
    m = _HEADER.match(subject)
    if not m:
        return None, False
    return m.group("type"), bool(m.group("bang"))


def decide_bump(subjects: list[str], bodies: list[str]) -> str | None:
    """The semver bump implied by a set of commits, or ``None`` for no release.

    An explicit "release"-named commit or PR (see ``_RELEASE_SIGNAL``), a feat,
    or any breaking change -> ``"minor"`` (pre-1.0: breaking stays minor);
    fix -> ``"patch"``; anything else on its own -> ``None``. The release signal
    forces the full minor bump (0.30.0 -> 0.31.0) regardless of the other
    commit types, so a release PR with no feat/fix still cuts a release.
    """
    breaking = any("BREAKING CHANGE" in b or "BREAKING-CHANGE" in b for b in bodies)
    has_feat = has_fix = release_signal = False
    for subject in subjects:
        if _RELEASE_SIGNAL.search(subject):
            release_signal = True
        ctype, bang = commit_type(subject)
        breaking = breaking or bang
        if ctype == "feat":
            has_feat = True
        elif ctype == "fix":
            has_fix = True
    if release_signal or breaking or has_feat:
        return "minor"
    if has_fix:
        return "patch"
    return None


def next_version(current: str, bump: str) -> str:
    """Apply ``bump`` (``"minor"``/``"patch"``) to a ``"X.Y.Z"`` string."""
    major, minor, patch = (int(p) for p in current.split("."))
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"unknown bump: {bump!r}")


def describe(subject: str) -> str:
    """Human changelog line for a subject: the description, with the scope (if
    any) kept as a bold lead. Non-conventional subjects pass through verbatim."""
    m = _HEADER.match(subject)
    if not m:
        return subject.strip()
    rest = subject[m.end() :].strip()
    scope = (m.group("scope") or "").strip("()")
    return f"**{scope}:** {rest}" if scope else rest


def render_notes(subjects: list[str]) -> str:
    """Group commit subjects into changelog sections (hidden types dropped)."""
    grouped: dict[str, list[str]] = {}
    for subject in subjects:
        ctype, _ = commit_type(subject)
        if ctype is not None:
            grouped.setdefault(ctype, []).append(subject)

    blocks: list[str] = []
    for ctype, heading in _SECTIONS:
        items = grouped.get(ctype)
        if not items:
            continue
        lines = [f"### {heading}", ""]
        lines += [f"- {describe(s)}" for s in items]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks).strip() or "Maintenance release."


# ----- side effects (exercised in CI, not unit-tested) ----------------------


def read_current_version() -> str:
    for line in PYPROJECT.read_text(encoding="utf-8").splitlines():
        m = re.match(r'^version\s*=\s*"([^"]+)"', line)
        if m:
            return m.group(1)
    raise SystemExit('error: no `version = "..."` line in pyproject.toml')


def write_version(version: str) -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    new = re.sub(
        r'^version\s*=\s*"[^"]+"',
        f'version = "{version}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    PYPROJECT.write_text(new, encoding="utf-8")


def prepend_changelog(version: str, notes: str) -> None:
    header = f"## {version} ({date.today().isoformat()})"
    entry = f"{header}\n\n{notes}\n"
    existing = CHANGELOG.read_text(encoding="utf-8") if CHANGELOG.is_file() else ""
    title, _, rest = existing.partition("\n")
    if title.strip().lower().startswith("# changelog"):
        CHANGELOG.write_text(f"{title}\n\n{entry}\n{rest.lstrip()}", encoding="utf-8")
    else:
        CHANGELOG.write_text(f"# Changelog\n\n{entry}\n{existing}", encoding="utf-8")


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def last_tag() -> str | None:
    try:
        return _git("describe", "--tags", "--abbrev=0", "--match", "v*")
    except subprocess.CalledProcessError:
        return None  # no release tag yet → first release covers all history


def commits_since(tag: str | None) -> list[tuple[str, str]]:
    """``(subject, body)`` for each commit after ``tag`` (all history if None)."""
    rev_range = f"{tag}..HEAD" if tag else "HEAD"
    # \x1e separates commits, \x1f separates subject from body within one.
    raw = _git("log", rev_range, "--no-merges", "--format=%s%x1f%b%x1e")
    commits: list[tuple[str, str]] = []
    for chunk in raw.split("\x1e"):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        subject, _, body = chunk.partition("\x1f")
        commits.append((subject.strip(), body.strip()))
    return commits


def emit_output(**pairs: str) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if not out:
        return
    with open(out, "a", encoding="utf-8") as fh:
        for key, value in pairs.items():
            fh.write(f"{key}={value}\n")


def main() -> int:
    tag = last_tag()
    commits = commits_since(tag)
    subjects = [s for s, _ in commits]
    bodies = [b for _, b in commits]

    bump = decide_bump(subjects, bodies)
    if bump is None:
        print(f"No releasable commits since {tag or 'repo start'} — skipping.")
        emit_output(released="false")
        return 0

    version = next_version(read_current_version(), bump)
    notes = render_notes(subjects)
    write_version(version)
    prepend_changelog(version, notes)
    NOTES_FILE.write_text(notes + "\n", encoding="utf-8")
    print(f"Releasing v{version} ({bump} bump, {len(commits)} commits).")
    emit_output(released="true", version=version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
