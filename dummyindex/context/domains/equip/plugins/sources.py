"""I/O for plugin discovery: probe tools, fetch marketplace catalogs, search
GitHub.

The ONLY equip module that shells out — isolated behind a ``Runner`` seam (a
callable taking argv and returning :class:`RunResult`) so tests inject a fake
and never touch the network. Mirrors the subprocess-in-domain precedent in
``context/build/git_delta.py``: fixed argv, no shell, never raises on non-zero.
"""

from __future__ import annotations

import base64
import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..errors import SourceError

CATALOG_PATH = ".claude-plugin/marketplace.json"


@dataclass(frozen=True)
class RunResult:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[list[str]], RunResult]


def default_runner(argv: list[str]) -> RunResult:
    """Run ``argv`` with no shell, capturing output. Never raises on non-zero;
    a missing executable surfaces as returncode 127."""
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return RunResult(returncode=127, stdout="", stderr=str(exc))
    return RunResult(proc.returncode, proc.stdout, proc.stderr)


@dataclass(frozen=True)
class ToolAvailability:
    claude: bool
    gh: bool
    git: bool


def available_tools(*, runner: Runner = default_runner) -> ToolAvailability:
    def has(tool: str) -> bool:
        return runner([tool, "--version"]).returncode == 0

    return ToolAvailability(claude=has("claude"), gh=has("gh"), git=has("git"))


def fetch_file(
    repo: str,
    path: str,
    *,
    ref: str | None = None,
    runner: Runner = default_runner,
) -> str | None:
    """Fetch one file's text from a GitHub repo via ``gh api`` contents.

    ``ref`` pins the fetch to a commit sha / branch / tag (the contents API
    ``?ref=`` query) so a vendored file is taken at the exact revision the user
    approved; ``None`` (default) fetches the default-branch HEAD, preserving the
    existing call sites. Returns ``None`` when the file/repo is absent (non-zero
    exit). Raises :class:`SourceError` when the response is present but
    undecodable.
    """
    endpoint = f"repos/{repo}/contents/{path}"
    if ref:
        endpoint = f"{endpoint}?ref={ref}"
    res = runner(["gh", "api", endpoint])
    if res.returncode != 0:
        return None
    try:
        obj = json.loads(res.stdout)
        if isinstance(obj, dict) and obj.get("encoding") == "base64":
            return base64.b64decode(obj["content"]).decode("utf-8")
        if isinstance(obj, dict):
            return str(obj.get("content", ""))
        raise SourceError(f"unexpected gh api response shape for {repo}/{path}")
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        raise SourceError(f"could not decode {path} from {repo}: {exc}") from exc


def fetch_catalog(
    repo: str, *, runner: Runner = default_runner
) -> dict[str, Any] | None:
    """Fetch + JSON-parse a repo's marketplace.json. ``None`` when absent."""
    text = fetch_file(repo, CATALOG_PATH, runner=runner)
    if text is None:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SourceError(f"{repo}/{CATALOG_PATH} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SourceError(f"{repo}/{CATALOG_PATH} is not a JSON object")
    return data


@dataclass(frozen=True)
class SkillRef:
    """One skill found in a collection repo: its ``name`` and the repo-relative
    ``path`` to the ``SKILL.md`` to fetch, plus the ``repo`` and pinned ``ref`` it
    was enumerated at. Content is fetched later (at install time) via
    :func:`fetch_file`."""

    name: str
    path: str
    repo: str
    ref: str | None = None


# Directories a collection repo conventionally keeps its skills under, tried in
# order; "" is the repo-root fallback (each top-level dir = one skill).
_SKILL_DIRS: tuple[str, ...] = ("skills", "")
_SKILL_FILE = "SKILL.md"


def _is_safe_skill_name(name: str) -> bool:
    """True when ``name`` is a single, visible path component safe to use as a
    skill directory.

    A collection's skill name becomes a path segment under ``.claude/skills/`` at
    install time, so reject empty, hidden (``.`` prefix — also rules out ``.``
    and ``..``), and any separator/traversal (``/``, ``\\``). Enumerating these
    out here means ``discover`` never even surfaces a crafted catalog entry that
    could escape the skills dir (defense-in-depth; the install boundary guards
    again)."""
    return (
        bool(name) and not name.startswith(".") and "/" not in name and "\\" not in name
    )


def resolve_ref(repo: str, *, runner: Runner = default_runner) -> str | None:
    """Resolve a repo's default-branch HEAD to a pinned commit sha.

    Returns ``None`` when the repo/commit is unreachable (non-zero exit); raises
    :class:`SourceError` when the response is present but undecodable. Pinning the
    ref at install time is what makes a vendored skill reproducible and immune to
    a moving-HEAD swap after the user approved its blast radius (concerns.md:13).
    """
    res = runner(["gh", "api", f"repos/{repo}/commits/HEAD"])
    if res.returncode != 0:
        return None
    try:
        obj = json.loads(res.stdout)
    except json.JSONDecodeError as exc:
        raise SourceError(f"could not decode HEAD commit for {repo}: {exc}") from exc
    if isinstance(obj, dict) and isinstance(obj.get("sha"), str):
        return obj["sha"]
    raise SourceError(f"unexpected commit response shape for {repo}")


def _list_dir(
    repo: str, path: str, *, ref: str | None, runner: Runner
) -> list[dict[str, Any]]:
    """List a repo directory's entries via the contents API.

    Returns ``[]`` when the directory is absent (non-zero exit) or the response
    is not a JSON array; raises :class:`SourceError` only when a present response
    is undecodable.
    """
    endpoint = f"repos/{repo}/contents/{path}" if path else f"repos/{repo}/contents"
    if ref:
        endpoint = f"{endpoint}?ref={ref}"
    res = runner(["gh", "api", endpoint])
    if res.returncode != 0:
        return []
    try:
        obj = json.loads(res.stdout)
    except json.JSONDecodeError as exc:
        label = path or "/"
        raise SourceError(
            f"could not decode {label} listing for {repo}: {exc}"
        ) from exc
    return [e for e in obj if isinstance(e, dict)] if isinstance(obj, list) else []


def list_skills(
    repo: str, *, ref: str | None = None, runner: Runner = default_runner
) -> tuple[SkillRef, ...]:
    """Enumerate the skills a collection repo ships, deterministically.

    A skill is a subdirectory holding a ``SKILL.md``. The conventional layouts in
    :data:`_SKILL_DIRS` are tried in order (``skills/<name>/`` then the repo root);
    the FIRST layout that yields any candidate wins, so a repo is never
    double-counted. Files, hidden dirs (``.github`` …), and any name that is not a
    safe single path component (:func:`_is_safe_skill_name`) are skipped — so a
    crafted entry can never become a traversal segment downstream. Results are
    sorted by name — the contents API order is not stable, and the caller's
    candidate ranking must not depend on arrival order. Membership of an actual
    ``SKILL.md`` is confirmed downstream by the install fetch (a miss skips it).
    """
    for base in _SKILL_DIRS:
        found: dict[str, SkillRef] = {}
        for entry in _list_dir(repo, base, ref=ref, runner=runner):
            if entry.get("type") != "dir":
                continue
            name = entry.get("name")
            if not isinstance(name, str) or not _is_safe_skill_name(name):
                continue
            entry_path = entry.get("path") or (f"{base}/{name}" if base else name)
            found[name] = SkillRef(
                name=name,
                path=f"{entry_path}/{_SKILL_FILE}",
                repo=repo,
                ref=ref,
            )
        if found:
            return tuple(found[name] for name in sorted(found))
    return ()


@dataclass(frozen=True)
class GitHubSearchResult:
    """The repos a search produced, plus whether the strategy degraded.

    ``degraded`` is True when ``gh search code`` failed (rate limit, auth) and
    the repos fallback — a different query with a different result universe —
    answered instead (or nothing answered). The CLI surfaces it loudly so
    run-to-run candidate churn is never a silent mystery.
    """

    repos: tuple[str, ...] = ()
    degraded: bool = False
    reason: str | None = None


def search_github(query: str, *, runner: Runner = default_runner) -> GitHubSearchResult:
    """Find repos that ship a marketplace.json, via GitHub code search.

    Tries ``gh search code`` for the catalog path + query (capped with
    ``--limit`` for a bounded result set); falls back to ``gh search repos``
    on failure, flagging the result ``degraded``. Returns owner/repo strings,
    deduped and SORTED — GitHub's code-search ordering is unstable, and the
    caller's first-wins name-collision logic must not depend on arrival order.
    """
    res = runner(
        [
            "gh",
            "search",
            "code",
            CATALOG_PATH,
            query,
            "--limit",
            "30",
            "--json",
            "repository",
            "--jq",
            ".[].repository.nameWithOwner",
        ]
    )
    degraded = False
    reason: str | None = None
    if res.returncode != 0:
        degraded = True
        reason = (res.stderr or "gh search code failed").strip()
        res = runner(["gh", "search", "repos", query, "--limit", "20"])
        if res.returncode != 0:
            return GitHubSearchResult(repos=(), degraded=True, reason=reason)
    repos: set[str] = set()
    for line in res.stdout.splitlines():
        token = line.strip().split()[0] if line.strip() else ""
        if token and "/" in token:
            repos.add(token)
    return GitHubSearchResult(
        repos=tuple(sorted(repos)), degraded=degraded, reason=reason
    )
