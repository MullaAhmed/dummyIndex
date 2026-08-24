"""RepoQA Searching-Needle-Function (SNF) suite adapter.

Source: the OFFICIAL RepoQA data drop — the gzipped JSON published on
``evalplus/repoqa_release`` GitHub releases (default version ``2024-06-23``,
the same artifact the ``repoqa`` PyPI package downloads; see their
``repoqa/data.py``). Schema::

    {"<lang>": [ {"repo": "org/name", "commit_sha": ..., "topic": ...,
                  "needles": [{"name", "description", "path",
                               "start_line", "end_line", ...},
                               ... x10],
                  "content": {path: source, ...},   # used only by grading
                  ...} x10 ]}

Languages in this drop: python, cpp, java, typescript, rust, go (600 needles).

Two task protocols, both giving the agent the pinned repo CHECKOUT instead of
the paper's stuffed 16K context (navigation is the capability under test):

- ``name`` — agent answers with ONLY the function name. Graded by the widely
  cited simplified rule: case-insensitive substring match
  (:mod:`benchmarks.scoring.snf`). Cheap, unambiguous, robust to verbosity.
- ``function`` — agent outputs the complete function code. Graded by the
  official evaluator, faithfully ported in :mod:`benchmarks.scoring.snf_official`:
  markdown sanitization -> tree-sitter function extraction -> smoothed BLEU
  best-match against every needle in the repo -> threshold (headline 0.8).

Both arms always share one protocol and one prompt, so any grading choice is
internally consistent; publish which protocol a number came from.
"""

from __future__ import annotations

import gzip
import json
import os
import random
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from benchmarks.arms import Arm, prepare_arm_workspace
from benchmarks.suites import SuiteDataError

RELEASE_URL_TEMPLATE = (
    "https://github.com/evalplus/repoqa_release/releases/download/"
    "{version}/repoqa-{version}.json.gz"
)
DEFAULT_DATA_VERSION = "2024-06-23"
DATA_OVERRIDE_ENV = "REPOQA_BENCH_DATA_OVERRIDE_PATH"
VERSION_ENV = "REPOQA_BENCH_DATA_VERSION"
DEFAULT_CACHE_SUBDIR = Path("results/benchmarks/cache/repoqa")

SUPPORTED_LANGS = ("python", "cpp", "java", "typescript", "rust", "go")

PROTOCOLS = ("name", "function")

NAME_INSTRUCTION = (
    "Search the repository for the function described below. "
    "Respond with ONLY the exact function name — no signature, no path, "
    "no explanation."
)

FUNCTION_INSTRUCTION = (
    "Search this repository checkout for the function described below. "
    "Respond with the COMPLETE code of that function — signature plus body, "
    "exactly as written in the repository — inside a fenced code block, and "
    "nothing else."
)


@dataclass(frozen=True)
class SnfTask:
    """One SNF task, normalized from the official release schema."""

    task_id: str
    language: str
    repo: str
    commit: str
    func: str
    description: str
    path: str
    start_line: int
    end_line: int

    @property
    def clone_url(self) -> str:
        return f"https://github.com/{self.repo}.git"


def _cache_dir(cache_dir: Path | None) -> Path:
    return cache_dir or DEFAULT_CACHE_SUBDIR


def _download_records(version: str, dest: Path) -> Path:
    url = RELEASE_URL_TEMPLATE.format(version=version)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp.gz")
    try:
        with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310
            payload = resp.read()
    except Exception as exc:
        raise SuiteDataError(
            f"failed to download RepoQA release {version} from {url}: {exc}"
        ) from exc
    tmp.write_bytes(payload)
    try:
        extracted = gzip.decompress(tmp.read_bytes())
    except Exception as exc:
        raise SuiteDataError(
            f"RepoQA release {version} is not valid gzip: {exc}"
        ) from exc
    dest.write_text(extracted.decode("utf-8"))
    tmp.unlink(missing_ok=True)
    return dest


def load_repoqa_records(
    cache_dir: Path | None = None,
    *,
    version: str | None = None,
) -> dict:
    """Load the official dataset JSON (cached; override paths supported).

    ``REPOQA_BENCH_DATA_OVERRIDE_PATH`` points at an already-extracted JSON;
    ``REPOQA_BENCH_DATA_VERSION`` selects a non-default release tag.
    """
    override = os.environ.get(DATA_OVERRIDE_ENV)
    if override:
        path = Path(override)
        if not path.exists():
            raise SuiteDataError(f"{DATA_OVERRIDE_ENV} file not found: {path}")
        return json.loads(path.read_text())
    version = version or os.environ.get(VERSION_ENV) or DEFAULT_DATA_VERSION
    target = _cache_dir(cache_dir) / f"repoqa-{version}.json"
    if not target.exists():
        _download_records(version, target)
    return json.loads(target.read_text())


def tasks_from_records(records: dict) -> list[SnfTask]:
    """Flatten the official nested schema into slim :class:`SnfTask` rows."""
    tasks: list[SnfTask] = []
    for language, repos in records.items():
        lang = str(language).strip().lower()
        if not isinstance(repos, list):
            raise SuiteDataError(f"language {language!r}: expected list of repos")
        for repo_record in repos:
            repo = repo_record.get("repo")
            commit = repo_record.get("commit_sha")
            needles = repo_record.get("needles") or []
            if not repo or not commit or not isinstance(needles, list):
                raise SuiteDataError(
                    f"language {language!r}: malformed repo record "
                    f"keys={sorted(repo_record)}"
                )
            for needle in needles:
                name = needle.get("name")
                desc = needle.get("description")
                npath = needle.get("path")
                start = needle.get("start_line")
                end = needle.get("end_line")
                if not all(
                    isinstance(v, (str, int)) and v is not None
                    for v in (name, desc, npath, start, end)
                ):
                    raise SuiteDataError(
                        f"{lang}/{repo}: malformed needle keys={sorted(needle)}"
                    )
                tasks.append(
                    SnfTask(
                        task_id=f"{lang}/{repo}/{name}",
                        language=lang,
                        repo=str(repo),
                        commit=str(commit),
                        func=str(name),
                        description=str(desc).strip(),
                        path=str(npath),
                        start_line=int(start),
                        end_line=int(end),
                    )
                )
    if not tasks:
        raise SuiteDataError("no SNF tasks found in records")
    return tasks


def load_repoqa_tasks(cache_dir: Path | None = None) -> list[SnfTask]:
    """Download-or-cache then flatten; the entry point used by the CLI."""
    return tasks_from_records(load_repoqa_records(cache_dir))


def repo_record(records: dict, language: str, repo: str) -> dict:
    """Look up one repo record (needed by the official grader for content)."""
    for candidate in records.get(language, []):
        if candidate.get("repo") == repo:
            return candidate
    raise SuiteDataError(f"no record for {language}/{repo}")


def select_subset(
    tasks: Sequence[SnfTask],
    *,
    per_lang_per_repo: int,
    seed: int,
) -> list[SnfTask]:
    """Deterministic stratified subset: N needles per (language, repo).

    Same seed always yields the same subset regardless of input ordering.
    """
    by_group: dict[tuple[str, str], list[SnfTask]] = {}
    for task in tasks:
        key = (task.language, task.repo)
        by_group.setdefault(key, []).append(task)
    rng = random.Random(seed)
    chosen: list[SnfTask] = []
    for key in sorted(by_group):
        group = sorted(by_group[key], key=lambda t: t.task_id)
        take = min(per_lang_per_repo, len(group))
        chosen.extend(rng.sample(group, take))
    return chosen


def build_prompt(task: SnfTask, *, protocol: str = "name") -> str:
    """Agent-facing prompt; identical across arms by construction."""
    if protocol == "name":
        instruction = NAME_INSTRUCTION
    elif protocol == "function":
        instruction = FUNCTION_INSTRUCTION
    else:
        raise ValueError(f"unknown protocol: {protocol!r}")
    return f"{instruction}\n\nFunction description:\n{task.description}"


def prepared_for_task(
    arm: Arm,
    task: SnfTask,
    *,
    workspace_root: Path,
    cache_root: Path,
    repeat: int | None = None,
    run_setup: Callable[..., None] | None = None,
) -> Path:
    return prepare_arm_workspace(
        arm,
        task.repo,
        task.commit,
        workspace_root,
        cache_root=cache_root,
        repeat=repeat,
        run_setup=run_setup,
    )


def workspace_for_task(
    arm: Arm,
    task,
    *,
    workspace_root: Path,
    cache_root: Path,
    repeat: int | None = None,
    run_setup=None,
) -> Path:
    """Path-only convenience; see :func:`prepared_for_task` for index_mode."""
    return prepared_for_task(
        arm,
        task,
        workspace_root=workspace_root,
        cache_root=cache_root,
        repeat=repeat,
        run_setup=run_setup,
    ).path


__all__ = [
    "DATA_OVERRIDE_ENV",
    "DEFAULT_CACHE_SUBDIR",
    "DEFAULT_DATA_VERSION",
    "FUNCTION_INSTRUCTION",
    "NAME_INSTRUCTION",
    "PROTOCOLS",
    "RELEASE_URL_TEMPLATE",
    "SUPPORTED_LANGS",
    "VERSION_ENV",
    "SnfTask",
    "SuiteDataError",
    "build_prompt",
    "load_repoqa_records",
    "load_repoqa_tasks",
    "prepared_for_task",
    "repo_record",
    "select_subset",
    "tasks_from_records",
    "workspace_for_task",
]
