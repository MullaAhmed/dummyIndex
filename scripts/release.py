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

Squash merges are handled explicitly. GitHub collapses a branch into one commit
titled after the PR — which defaults to the *branch name*, e.g.
``Feat/curated codebase scan (#10)``, a slash rather than a ``:`` and therefore
not a conventional header — while the real commits survive only as ``* ``
bullets in the body. Reading subjects alone silently skipped the release for
PRs #9 and #10, so ``effective_subjects`` folds those bullets back in.

``--channel beta`` (pushes to ``development``) applies the same bump to cut a
PEP 440 pre-release, ``X.Y.ZbN``. pip skips it unless asked (``--pre`` or an
exact pin). The bump is written for the tag only, never committed to the
branch, so ``development`` keeps the stable version and no bot commit reaches
``main``'s commit range. No CHANGELOG entry for betas.

The decision functions take plain data so they can be tested without git.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from datetime import date
from pathlib import Path

# `type(scope)!:` — the conventional-commit header. `bang` (`!`) and a
# `BREAKING CHANGE:` body trailer both mark a breaking change.
_HEADER = re.compile(r"^(?P<type>\w+)(?P<scope>\([^)]*\))?(?P<bang>!)?:")

# One squashed commit inside a squash-merge body. GitHub's "Squash and merge"
# collapses a branch into a single commit whose *subject* is the PR title —
# which defaults to the branch name (`Feat/curated codebase scan (#10)`), not a
# conventional header — and lists the real commits as `* `-prefixed body lines.
# Asterisk only, deliberately: prose written inside a commit message uses `- `,
# and treating those as commits would inflate both the bump and the notes.
_SQUASH_BULLET = re.compile(r"^[ \t]*\*[ \t]+(?P<subject>.+?)[ \t]*$", re.MULTILINE)

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


def squashed_subjects(body: str) -> list[str]:
    """Conventional-commit subjects recovered from a squash-merge ``body``.

    Only ``* `` bullets that parse as conventional headers are returned, so
    ordinary prose (and GitHub's bullets for un-conventional commits) is
    ignored.
    """
    return [
        m.group("subject")
        for m in _SQUASH_BULLET.finditer(body)
        if commit_type(m.group("subject"))[0] is not None
    ]


def effective_subjects(commits: list[tuple[str, str]]) -> list[str]:
    """The subjects a release decision should actually see.

    A commit whose own subject is a conventional header is authoritative and is
    used as-is — a maintainer-written PR title already describes the squash, and
    expanding it too would duplicate every line in the changelog. A commit whose
    subject is *not* conventional is most likely a squash merge titled after its
    branch, so its body's ``* `` bullets are folded in; that is the only way the
    `feat`/`fix` inside such a PR can be seen at all.
    """
    subjects: list[str] = []
    for subject, body in commits:
        subjects.append(subject)
        if commit_type(subject)[0] is None:
            subjects.extend(squashed_subjects(body))
    return subjects


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


def next_beta_version(target: str, tags: list[str]) -> str | None:
    """``{target}bN`` with N one past the highest existing ``v{target}bN`` tag.

    ``None`` when ``v{target}`` is already released: ``development`` is behind
    ``main`` and a beta of a shipped version would sort below it.
    """
    if f"v{target}" in tags:
        return None
    pattern = re.compile(rf"^v{re.escape(target)}b(\d+)$")
    numbers = [int(m.group(1)) for t in tags if (m := pattern.match(t))]
    return f"{target}b{max(numbers, default=0) + 1}"


def beta_notes(version: str, notes: str) -> str:
    """Release notes for a beta, led by the opt-in install commands."""
    return (
        f"Pre-release. `pip install dummyindex` skips it; install with "
        f"`pip install dummyindex=={version}` or `pip install --pre dummyindex`.\n\n"
        f"{notes}"
    )


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
    """Nearest stable ``vX.Y.Z`` tag; beta tags (a letter after the ``v``) are skipped."""
    try:
        return _git(
            "describe", "--tags", "--abbrev=0", "--match", "v*", "--exclude", "v*[a-z]*"
        )
    except subprocess.CalledProcessError:
        return None  # no release tag yet → first release covers all history


def all_tags() -> list[str]:
    return _git("tag", "--list", "v*").splitlines()


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--channel", choices=("stable", "beta"), default="stable")
    channel = parser.parse_args(argv).channel

    tag = last_tag()
    commits = commits_since(tag)
    subjects = effective_subjects(commits)
    bodies = [b for _, b in commits]

    bump = decide_bump(subjects, bodies)
    if bump is None:
        print(f"No releasable commits since {tag or 'repo start'} — skipping.")
        emit_output(released="false", channel=channel)
        return 0

    target = next_version(read_current_version(), bump)
    notes = render_notes(subjects)
    if channel == "beta":
        version = next_beta_version(target, all_tags())
        if version is None:
            print(f"v{target} is already released; merge main into development first.")
            emit_output(released="false", channel=channel)
            return 0
        write_version(version)
        NOTES_FILE.write_text(beta_notes(version, notes) + "\n", encoding="utf-8")
    else:
        version = target
        write_version(version)
        prepend_changelog(version, notes)
        NOTES_FILE.write_text(notes + "\n", encoding="utf-8")
    print(f"Releasing v{version} ({channel}, {bump} bump, {len(commits)} commits).")
    emit_output(released="true", version=version, channel=channel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
