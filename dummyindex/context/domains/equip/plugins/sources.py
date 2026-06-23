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


def fetch_file(repo: str, path: str, *, runner: Runner = default_runner) -> str | None:
    """Fetch one file's text from a GitHub repo via ``gh api`` contents.

    Returns ``None`` when the file/repo is absent (non-zero exit). Raises
    :class:`SourceError` when the response is present but undecodable.
    """
    res = runner(["gh", "api", f"repos/{repo}/contents/{path}"])
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
