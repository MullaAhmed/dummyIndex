# Parallel Council Dispatch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the council's serial per-feature loop with a deterministic `council-batch --next` CLI verb (the council twin of build's `--next-wave`) so the Claude session can dispatch independent features' agents in parallel, stage by stage.

**Architecture:** A new pure domain module computes the *earliest incomplete stage* across all non-trivial features (from `features/INDEX.json` + per-feature `_council-log.json`) and returns up to `--cap` dispatch-units, each annotated with its `subagent_type` (reusing `pick_dev` for dev-authored stages, a fixed map for architect/critics). A new wire-only CLI verb prints that batch as JSON. The council skill loops `--next` → dispatch-in-parallel → barrier until the CLI reports `complete`. Resumption is free (the frontier is recomputed from the logs each call); failures isolate per-feature.

**Tech Stack:** Python 3.10+, stdlib only (`dataclasses`, `enum`, `json`, `pathlib`), `pytest`, `uv`. Follows the repo's frozen-dataclass / enum-constant / typed-exception / strict-layering / wire-only-CLI conventions.

---

## File Structure

| Path | New/Modify | Responsibility |
|---|---|---|
| `dummyindex/context/domains/council_batch.py` | Create | Pure batch logic: `CouncilStage`, `CouncilMode`, `CRITIC_ROSTER`, `active_stages`, `earliest_incomplete_stage`, `DispatchUnit`, `Batch`, `next_batch`. |
| `dummyindex/context/domains/dev_pick.py` | Modify | Add two public helpers `harvest_dep_tokens(repo_root)` + `read_feature_files(features_dir, feature_id)` (relocated from `cli/dev_pick.py`) so the domain — not the CLI — owns the I/O `council_batch` needs. |
| `dummyindex/cli/dev_pick.py` | Modify | Call the relocated domain helpers instead of its local `_harvest_dep_tokens` / `_read_feature_files` (behaviour identical). |
| `dummyindex/cli/council_batch.py` | Create | Wire-only `context council-batch --next` verb: parse flags, call `next_batch`, print JSON / human. |
| `dummyindex/context/enums.py` | Modify | Add `COUNCIL_BATCH = "council-batch"`. |
| `dummyindex/cli/__init__.py` | Modify | Import `council_batch`, register `ContextSubcommand.COUNCIL_BATCH: council_batch.run`. |
| `dummyindex/cli/help.py` | Modify | Document the verb in `USAGE`. |
| `dummyindex/skills/council/00-overview.md` | Modify | Replace the "SEQUENTIAL per feature" sequencing with the batched-parallel loop. |
| `dummyindex/skills/council/22-parallel-dispatch.md` | Create | The conductor procedure (`--next` loop, parallel dispatch, barrier, failure isolation, end-report). |
| `dummyindex/skills/council/19-resume.md` | Modify | Note resumption is per-stage via `--next` recomputation. |
| `dummyindex/skills/skill.md` | Modify | Update Phase 2/3 description away from strict per-feature serialism. |
| `tests/context/domains/test_council_batch.py` | Create | Domain unit tests. |
| `tests/context/domains/test_council_batch_cli.py` | Create | CLI verb tests. |
| `pyproject.toml` | Modify | `version = "0.20.0"`. |
| `CHANGELOG.md` | Modify | `0.20.0` entry. |

### Deterministic critic roster (a decision encoded here — confirm at review)

The domain must resolve stage-3 critics deterministically (no "relevance" judgment in pure code). Roster by mode:

- **light** → `()` — no critique stage at all.
- **standard** → `(critic-security → Security Engineer)` — one critic; security is the most universally applicable.
- **deep** → `(critic-database → Data Engineer, critic-security → Security Engineer, critic-product → general-purpose)` — all three.

This trades per-feature critic-relevance pruning (previously a skill judgment) for deterministic batching. `40-critique.md` is aligned to this roster in Task 9.

---

## Task 1: `CouncilStage` / `CouncilMode` enums + `active_stages`

**Files:**
- Create: `dummyindex/context/domains/council_batch.py`
- Test: `tests/context/domains/test_council_batch.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/context/domains/test_council_batch.py
from dummyindex.context.domains.council_batch import (
    CouncilStage,
    CouncilMode,
    active_stages,
)


def test_council_stage_numbers_match_log_convention():
    assert CouncilStage.SPECIFY == 1
    assert CouncilStage.PLAN == 2
    assert CouncilStage.CRITIQUE == 3
    assert CouncilStage.FLOW == 4
    assert CouncilStage.TREE == 5


def test_active_stages_light_skips_plan_and_critique():
    assert active_stages(CouncilMode.LIGHT, tree_enrich=False) == (
        CouncilStage.SPECIFY,
        CouncilStage.FLOW,
    )


def test_active_stages_standard_is_full_minus_tree():
    assert active_stages(CouncilMode.STANDARD, tree_enrich=False) == (
        CouncilStage.SPECIFY,
        CouncilStage.PLAN,
        CouncilStage.CRITIQUE,
        CouncilStage.FLOW,
    )


def test_active_stages_deep_with_tree_includes_tree_last():
    assert active_stages(CouncilMode.DEEP, tree_enrich=True) == (
        CouncilStage.SPECIFY,
        CouncilStage.PLAN,
        CouncilStage.CRITIQUE,
        CouncilStage.FLOW,
        CouncilStage.TREE,
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/context/domains/test_council_batch.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'dummyindex.context.domains.council_batch'`

- [ ] **Step 3: Write minimal implementation**

```python
# dummyindex/context/domains/council_batch.py
"""Parallel-council batch frontier — the council twin of build's `next_wave`.

The serial council loop processed one feature at a time. This module computes,
deterministically and with no LLM, the *earliest incomplete stage* across all
non-trivial features and the dispatch-units for that stage, so the council
skill can fan independent features out to parallel Task subagents.

Stage numbers match the council-log convention (`council/00-overview.md`):
specify=1, plan=2, critique=3 — extended here with flow=4, tree-enrich=5.
"""
from __future__ import annotations

from enum import Enum, IntEnum


class CouncilStage(IntEnum):
    """The ordered council stages, numbered as written to `_council-log.json`."""

    SPECIFY = 1
    PLAN = 2
    CRITIQUE = 3
    FLOW = 4
    TREE = 5


class CouncilMode(str, Enum):
    """Council depth modes (passed via `/dummyindex --mode`)."""

    LIGHT = "light"
    STANDARD = "standard"
    DEEP = "deep"


def active_stages(mode: CouncilMode, *, tree_enrich: bool) -> tuple[CouncilStage, ...]:
    """The stages that actually run for ``mode``.

    light = dev only (specify) + flow; standard/deep add plan + critique.
    Tree-enrich is mode-gated and appended only when ``tree_enrich`` is set.
    """
    stages: list[CouncilStage] = [CouncilStage.SPECIFY]
    if mode in (CouncilMode.STANDARD, CouncilMode.DEEP):
        stages.append(CouncilStage.PLAN)
        stages.append(CouncilStage.CRITIQUE)
    stages.append(CouncilStage.FLOW)
    if tree_enrich:
        stages.append(CouncilStage.TREE)
    return tuple(stages)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/context/domains/test_council_batch.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/domains/council_batch.py tests/context/domains/test_council_batch.py
git commit -m "feat(council): CouncilStage/CouncilMode enums + active_stages"
```

---

## Task 2: Relocate dev-pick I/O helpers into the domain layer

**Why:** `council_batch` needs to read a feature's files and harvest dependency tokens to call `pick_dev`. Those helpers currently live in `cli/dev_pick.py` (CLI layer). Strict layering forbids a domain importing the CLI, so move them into the `dev_pick` domain and have the CLI call them. Behaviour is identical.

**Files:**
- Modify: `dummyindex/context/domains/dev_pick.py` (add public helpers at end)
- Modify: `dummyindex/cli/dev_pick.py:_read_feature_files`, `:_harvest_dep_tokens`, `:run`
- Test: `tests/context/domains/test_council_batch.py` (add cases)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/context/domains/test_council_batch.py
import json
from dummyindex.context.domains.dev_pick import (
    harvest_dep_tokens,
    read_feature_files,
)


def _make_feature(features_dir, feature_id, files):
    fdir = features_dir / feature_id
    fdir.mkdir(parents=True)
    (fdir / "feature.json").write_text(
        json.dumps({"feature_id": feature_id, "files": list(files)}),
        encoding="utf-8",
    )
    return fdir


def test_read_feature_files_returns_tuple(tmp_path):
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "auth", ["src/auth.py", "src/login.py"])
    assert read_feature_files(features_dir, "auth") == ("src/auth.py", "src/login.py")


def test_read_feature_files_missing_raises(tmp_path):
    features_dir = tmp_path / ".context" / "features"
    features_dir.mkdir(parents=True)
    import pytest
    with pytest.raises(FileNotFoundError):
        read_feature_files(features_dir, "ghost")


def test_harvest_dep_tokens_reads_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        'dependencies = ["fastapi", "sqlalchemy"]\n', encoding="utf-8"
    )
    tokens = harvest_dep_tokens(tmp_path)
    assert "fastapi" in tokens
    assert "sqlalchemy" in tokens
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/context/domains/test_council_batch.py -q`
Expected: FAIL — `ImportError: cannot import name 'harvest_dep_tokens' from 'dummyindex.context.domains.dev_pick'`

- [ ] **Step 3: Write minimal implementation**

Add to the **end** of `dummyindex/context/domains/dev_pick.py` (the regexes `_TOKEN_RE`, `_PROSE_KEY_RE`, `_MANIFEST_NAMES` and `_is_noise_line` referenced below are *moved here from `cli/dev_pick.py`* — paste their exact current definitions from that file into this module, above these functions, if they are not already present):

```python
import re as _re  # if `re` is not already imported at module top, use the top-level import instead
from pathlib import Path as _Path


# --- feature/manifest I/O (relocated from cli/dev_pick.py so domains own it) --

_MANIFEST_NAMES: tuple[str, ...] = (
    "pyproject.toml",
    "requirements.txt",
    "setup.cfg",
    "package.json",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "go.mod",
    "Cargo.toml",
)

_TOKEN_RE = _re.compile(r"[a-z0-9_-]+")

_PROSE_KEY_RE = _re.compile(
    r'^\s*"?(description|summary|readme|keywords|authors?|maintainers?|name'
    r"|license|homepage|documentation|repository|classifiers)\"?\s*[=:]",
    _re.IGNORECASE,
)


def _is_noise_line(line: str) -> bool:
    stripped = line.lstrip()
    if stripped.startswith("#") or stripped.startswith("//"):
        return True
    return _PROSE_KEY_RE.match(line) is not None


def harvest_dep_tokens(repo_root: _Path) -> frozenset[str]:
    """Lowercased dependency tokens harvested from whichever root manifests exist.

    Tolerates missing/unreadable files. Skips comment + prose-bearing lines so a
    `description = "A Django-style framework"` doesn't misroute the repo.
    """
    tokens: set[str] = set()
    for name in _MANIFEST_NAMES:
        path = repo_root / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            if _is_noise_line(line):
                continue
            tokens.update(_TOKEN_RE.findall(line.lower()))
    return frozenset(tokens)


def read_feature_files(features_dir: _Path, feature_id: str) -> tuple[str, ...]:
    """The feature's ``files`` list from ``features/<id>/feature.json``.

    Raises ``FileNotFoundError`` if the feature.json is absent.
    """
    import json as _json

    feature_json = features_dir / feature_id / "feature.json"
    if not feature_json.is_file():
        raise FileNotFoundError(str(feature_json))
    data = _json.loads(feature_json.read_text(encoding="utf-8"))
    return tuple(str(f) for f in data.get("files", []))
```

> NOTE for the implementer: prefer reusing the module's existing top-level `import re`, `import json`, and `from pathlib import Path` rather than the aliased imports shown above — the aliases are only to make this code block self-contained. Keep one definition of each regex/constant; if `dev_pick.py` already defines them at module scope, don't duplicate — reference the existing ones.

Now rewrite `cli/dev_pick.py` to delegate. Replace its `_read_feature_files`, `_harvest_dep_tokens`, `_is_noise_line`, and the module-level `_MANIFEST_NAMES`/`_TOKEN_RE`/`_PROSE_KEY_RE` with imports, and update `run`:

```python
# dummyindex/cli/dev_pick.py  (new body)
"""`dummyindex context dev-pick --feature ID` — stack-aware author picker.

Thin CLI: resolves the feature's files + the repo's dependency tokens via the
`dev_pick` domain helpers, calls `pick_dev`, prints the JSON. Deterministic.
"""
from __future__ import annotations

import json
import sys

from .common import parse_kv_flags, parse_path_and_root, resolve_context_root


def run(args: list[str]) -> int:
    from dummyindex.context.domains.dev_pick import (
        harvest_dep_tokens,
        pick_dev,
        read_feature_files,
    )

    scope, explicit_root, rest = parse_path_and_root(args)
    parsed, leftover = parse_kv_flags(rest)
    if leftover:
        print(f"error: unknown argument(s) for `dev-pick`: {leftover}", file=sys.stderr)
        return 2
    feature_id = parsed.get("feature")
    if not feature_id:
        print("error: --feature <id> is required", file=sys.stderr)
        return 2

    repo_root = resolve_context_root(scope, explicit_root=explicit_root)
    features_dir = repo_root / ".context" / "features"

    try:
        feature_files = read_feature_files(features_dir, feature_id)
    except FileNotFoundError as exc:
        print(f"error: feature {feature_id} not found ({exc})", file=sys.stderr)
        return 2

    dep_tokens = harvest_dep_tokens(repo_root)
    pick = pick_dev(feature_files=feature_files, dep_tokens=dep_tokens)
    print(json.dumps(pick.to_dict()))
    return 0
```

- [ ] **Step 4: Run tests (new + existing dev-pick regression)**

Run: `uv run pytest tests/context/domains/test_council_batch.py tests/context/domains/test_dev_pick.py -q`
Expected: PASS — new helper tests pass AND the existing `test_dev_pick.py` suite still passes (proves the CLI relocation is behaviour-preserving).

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/domains/dev_pick.py dummyindex/cli/dev_pick.py tests/context/domains/test_council_batch.py
git commit -m "refactor(dev-pick): relocate feature/manifest I/O helpers into domain layer"
```

---

## Task 3: `earliest_incomplete_stage` + per-feature readiness

**Files:**
- Modify: `dummyindex/context/domains/council_batch.py`
- Test: `tests/context/domains/test_council_batch.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/context/domains/test_council_batch.py
from dummyindex.context.domains.council_batch import earliest_incomplete_stage
from dummyindex.context.domains.council import append_log


def _log(features_dir, feature_id, stage, agent, status):
    append_log(features_dir, feature_id=feature_id, stage=stage, agent=agent, status=status)


def test_earliest_stage_is_specify_when_nothing_logged(tmp_path):
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _make_feature(features_dir, "b", ["b.py"])
    stage = earliest_incomplete_stage(
        features_dir, ("a", "b"), mode=CouncilMode.STANDARD, tree_enrich=False
    )
    assert stage == CouncilStage.SPECIFY


def test_earliest_stage_advances_to_plan_once_all_specify_done(tmp_path):
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _make_feature(features_dir, "b", ["b.py"])
    for fid in ("a", "b"):
        _log(features_dir, fid, 1, "dev", "started")
        _log(features_dir, fid, 1, "dev", "complete")
    stage = earliest_incomplete_stage(
        features_dir, ("a", "b"), mode=CouncilMode.STANDARD, tree_enrich=False
    )
    assert stage == CouncilStage.PLAN


def test_earliest_stage_stays_at_specify_if_one_feature_incomplete(tmp_path):
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _make_feature(features_dir, "b", ["b.py"])
    _log(features_dir, "a", 1, "dev", "started")
    _log(features_dir, "a", 1, "dev", "complete")
    # b never started specify
    stage = earliest_incomplete_stage(
        features_dir, ("a", "b"), mode=CouncilMode.STANDARD, tree_enrich=False
    )
    assert stage == CouncilStage.SPECIFY


def test_earliest_stage_none_when_all_active_stages_done(tmp_path):
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    for stage, agent in ((1, "dev"), (4, "dev")):  # light mode active stages
        _log(features_dir, "a", stage, agent, "started")
        _log(features_dir, "a", stage, agent, "complete")
    stage = earliest_incomplete_stage(
        features_dir, ("a",), mode=CouncilMode.LIGHT, tree_enrich=False
    )
    assert stage is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/context/domains/test_council_batch.py -q`
Expected: FAIL — `ImportError: cannot import name 'earliest_incomplete_stage'`

- [ ] **Step 3: Write minimal implementation**

Append to `dummyindex/context/domains/council_batch.py`:

```python
from pathlib import Path
from typing import Optional

from dummyindex.context.domains.council import is_stage_complete


def earliest_incomplete_stage(
    features_dir: Path,
    feature_ids: tuple[str, ...],
    *,
    mode: CouncilMode,
    tree_enrich: bool,
) -> Optional[CouncilStage]:
    """The lowest active stage not yet complete for *every* feature, or None.

    A stage ``S`` is the frontier iff at least one feature has not completed it.
    Returns None when every feature has completed every active stage.
    """
    for stage in active_stages(mode, tree_enrich=tree_enrich):
        if any(
            not is_stage_complete(features_dir, fid, int(stage))
            for fid in feature_ids
        ):
            return stage
    return None


def _prior_active_stage(
    stage: CouncilStage, mode: CouncilMode, *, tree_enrich: bool
) -> Optional[CouncilStage]:
    """The active stage immediately before ``stage``, or None if it is first."""
    stages = active_stages(mode, tree_enrich=tree_enrich)
    idx = stages.index(stage)
    return stages[idx - 1] if idx > 0 else None


def _feature_ready_for(
    features_dir: Path,
    feature_id: str,
    stage: CouncilStage,
    mode: CouncilMode,
    *,
    tree_enrich: bool,
) -> bool:
    """True iff ``feature_id`` needs ``stage`` and its prior active stage is done."""
    if is_stage_complete(features_dir, feature_id, int(stage)):
        return False  # already done this stage
    prior = _prior_active_stage(stage, mode, tree_enrich=tree_enrich)
    if prior is None:
        return True
    return is_stage_complete(features_dir, feature_id, int(prior))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/context/domains/test_council_batch.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/domains/council_batch.py tests/context/domains/test_council_batch.py
git commit -m "feat(council): earliest-incomplete-stage frontier + per-feature readiness"
```

---

## Task 4: `DispatchUnit`, `Batch`, and `next_batch` for dev/architect stages

**Files:**
- Modify: `dummyindex/context/domains/council_batch.py`
- Test: `tests/context/domains/test_council_batch.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/context/domains/test_council_batch.py
from dummyindex.context.domains.council_batch import next_batch


def test_next_batch_specify_emits_one_dev_unit_per_feature(tmp_path):
    repo_root = tmp_path
    features_dir = repo_root / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _make_feature(features_dir, "b", ["b.py"])
    batch = next_batch(
        features_dir, repo_root, ("a", "b"),
        mode=CouncilMode.STANDARD, cap=8, tree_enrich=False,
    )
    assert batch.complete is False
    assert batch.stage == CouncilStage.SPECIFY
    assert [u.feature_id for u in batch.units] == ["a", "b"]
    assert all(u.role == "dev" for u in batch.units)
    # dev subagent_type resolved via pick_dev (Senior Developer fallback here)
    assert all(u.subagent_type for u in batch.units)
    assert all(u.stage == 1 for u in batch.units)


def test_next_batch_plan_emits_architect_units(tmp_path):
    repo_root = tmp_path
    features_dir = repo_root / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _log(features_dir, "a", 1, "dev", "started")
    _log(features_dir, "a", 1, "dev", "complete")
    batch = next_batch(
        features_dir, repo_root, ("a",),
        mode=CouncilMode.STANDARD, cap=8, tree_enrich=False,
    )
    assert batch.stage == CouncilStage.PLAN
    assert len(batch.units) == 1
    unit = batch.units[0]
    assert unit.role == "architect"
    assert unit.subagent_type == "Backend Architect"
    assert unit.framework is None


def test_next_batch_complete_when_all_done(tmp_path):
    repo_root = tmp_path
    features_dir = repo_root / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    for stage, agent in ((1, "dev"), (4, "dev")):
        _log(features_dir, "a", stage, agent, "started")
        _log(features_dir, "a", stage, agent, "complete")
    batch = next_batch(
        features_dir, repo_root, ("a",),
        mode=CouncilMode.LIGHT, cap=8, tree_enrich=False,
    )
    assert batch.complete is True
    assert batch.stage is None
    assert batch.units == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/context/domains/test_council_batch.py -q`
Expected: FAIL — `ImportError: cannot import name 'next_batch'`

- [ ] **Step 3: Write minimal implementation**

Append to `dummyindex/context/domains/council_batch.py`:

```python
from dataclasses import dataclass

from dummyindex.context.domains.dev_pick import (
    harvest_dep_tokens,
    pick_dev,
    read_feature_files,
)


@dataclass(frozen=True)
class DispatchUnit:
    """One Task-tool agent invocation the council skill must launch."""

    feature_id: str
    stage: int
    role: str          # council-log --agent AND persona-file selector
    subagent_type: str  # the Task-tool agent to launch
    framework: Optional[str]  # dev-authored stages only; else None

    def to_dict(self) -> dict:
        return {
            "feature_id": self.feature_id,
            "stage": self.stage,
            "role": self.role,
            "subagent_type": self.subagent_type,
            "framework": self.framework,
        }


@dataclass(frozen=True)
class Batch:
    """The dispatch frontier for one `--next` call."""

    complete: bool
    stage: Optional[CouncilStage]
    units: tuple[DispatchUnit, ...]


_ARCHITECT_SUBAGENT = "Backend Architect"


def _dev_unit(
    feature_id: str, stage: CouncilStage, features_dir: Path, dep_tokens
) -> DispatchUnit:
    """A dev-authored unit (specify / flow / tree) with stack-resolved subagent."""
    try:
        files = read_feature_files(features_dir, feature_id)
    except FileNotFoundError:
        files = ()
    pick = pick_dev(feature_files=files, dep_tokens=dep_tokens)
    return DispatchUnit(
        feature_id=feature_id,
        stage=int(stage),
        role="dev",
        subagent_type=str(pick.subagent_type),
        framework=pick.framework,
    )


def _units_for_feature(
    feature_id: str,
    stage: CouncilStage,
    features_dir: Path,
    dep_tokens,
    mode: CouncilMode,
) -> tuple[DispatchUnit, ...]:
    """Expand one feature at ``stage`` into its dispatch-unit(s)."""
    if stage in (CouncilStage.SPECIFY, CouncilStage.FLOW, CouncilStage.TREE):
        return (_dev_unit(feature_id, stage, features_dir, dep_tokens),)
    if stage == CouncilStage.PLAN:
        return (
            DispatchUnit(
                feature_id=feature_id,
                stage=int(stage),
                role="architect",
                subagent_type=_ARCHITECT_SUBAGENT,
                framework=None,
            ),
        )
    # CRITIQUE handled in Task 5; placeholder keeps this task's tests green.
    return ()


def next_batch(
    features_dir: Path,
    repo_root: Path,
    feature_ids: tuple[str, ...],
    *,
    mode: CouncilMode,
    cap: int,
    tree_enrich: bool,
) -> Batch:
    """Compute the next dispatch batch — the council twin of ``next_wave``.

    Picks the earliest incomplete active stage, gathers the features ready for
    it (prior stage complete), expands each to its unit(s), and returns up to
    ``cap`` units (agent-bounded; a single feature's units are never split).
    """
    if cap < 1:
        raise ValueError(f"cap must be >= 1, got {cap}")

    stage = earliest_incomplete_stage(
        features_dir, feature_ids, mode=mode, tree_enrich=tree_enrich
    )
    if stage is None:
        return Batch(complete=True, stage=None, units=())

    dep_tokens = harvest_dep_tokens(repo_root)
    collected: list[DispatchUnit] = []
    for fid in feature_ids:
        if not _feature_ready_for(
            features_dir, fid, stage, mode, tree_enrich=tree_enrich
        ):
            continue
        feature_units = _units_for_feature(
            fid, stage, features_dir, dep_tokens, mode
        )
        if not feature_units:
            continue
        if collected and len(collected) + len(feature_units) > cap:
            break  # honour cap at feature granularity (never split a feature)
        collected.extend(feature_units)
    return Batch(complete=False, stage=stage, units=tuple(collected))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/context/domains/test_council_batch.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/domains/council_batch.py tests/context/domains/test_council_batch.py
git commit -m "feat(council): next_batch frontier for dev + architect stages"
```

---

## Task 5: Critique-stage roster expansion + agent-bounded cap

**Files:**
- Modify: `dummyindex/context/domains/council_batch.py`
- Test: `tests/context/domains/test_council_batch.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/context/domains/test_council_batch.py
from dummyindex.context.domains.council_batch import CRITIC_ROSTER


def _complete_through_plan(features_dir, fid):
    for stage, agent in ((1, "dev"), (2, "architect")):
        _log(features_dir, fid, stage, agent, "started")
        _log(features_dir, fid, stage, agent, "complete")


def test_critic_roster_sizes_per_mode():
    assert CRITIC_ROSTER[CouncilMode.LIGHT] == ()
    assert len(CRITIC_ROSTER[CouncilMode.STANDARD]) == 1
    assert len(CRITIC_ROSTER[CouncilMode.DEEP]) == 3


def test_critique_deep_emits_one_unit_per_feature_per_critic(tmp_path):
    repo_root = tmp_path
    features_dir = repo_root / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _complete_through_plan(features_dir, "a")
    batch = next_batch(
        features_dir, repo_root, ("a",),
        mode=CouncilMode.DEEP, cap=8, tree_enrich=False,
    )
    assert batch.stage == CouncilStage.CRITIQUE
    roles = sorted(u.role for u in batch.units)
    assert roles == ["critic-database", "critic-product", "critic-security"]
    subs = {u.role: u.subagent_type for u in batch.units}
    assert subs["critic-database"] == "Data Engineer"
    assert subs["critic-security"] == "Security Engineer"
    assert subs["critic-product"] == "general-purpose"


def test_cap_counts_agents_across_features(tmp_path):
    repo_root = tmp_path
    features_dir = repo_root / ".context" / "features"
    for fid in ("a", "b", "c"):
        _make_feature(features_dir, fid, [f"{fid}.py"])
        _complete_through_plan(features_dir, fid)
    # deep critique = 3 agents/feature; cap=4 ⇒ only the first feature fits
    batch = next_batch(
        features_dir, repo_root, ("a", "b", "c"),
        mode=CouncilMode.DEEP, cap=4, tree_enrich=False,
    )
    assert len({u.feature_id for u in batch.units}) == 1
    assert len(batch.units) == 3


def test_single_feature_critics_never_split_even_under_cap(tmp_path):
    repo_root = tmp_path
    features_dir = repo_root / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _complete_through_plan(features_dir, "a")
    batch = next_batch(
        features_dir, repo_root, ("a",),
        mode=CouncilMode.DEEP, cap=2, tree_enrich=False,  # cap < roster size
    )
    assert len(batch.units) == 3  # the one feature's full roster, never split
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/context/domains/test_council_batch.py -q`
Expected: FAIL — `ImportError: cannot import name 'CRITIC_ROSTER'` (and critique units empty)

- [ ] **Step 3: Write minimal implementation**

In `dummyindex/context/domains/council_batch.py`, add the roster constant near the top (after `CouncilMode`):

```python
# Deterministic critic roster by mode: (role, subagent_type) pairs.
# light = no critique; standard = one critic (security, the most universal);
# deep = all three. Replaces per-feature "relevance" judgment with a fixed,
# resumable roster — see 22-parallel-dispatch.md / 40-critique.md.
CRITIC_ROSTER: dict["CouncilMode", tuple[tuple[str, str], ...]] = {
    CouncilMode.LIGHT: (),
    CouncilMode.STANDARD: (("critic-security", "Security Engineer"),),
    CouncilMode.DEEP: (
        ("critic-database", "Data Engineer"),
        ("critic-security", "Security Engineer"),
        ("critic-product", "general-purpose"),
    ),
}
```

Replace the `# CRITIQUE handled in Task 5` branch in `_units_for_feature` with:

```python
    if stage == CouncilStage.CRITIQUE:
        return tuple(
            DispatchUnit(
                feature_id=feature_id,
                stage=int(stage),
                role=role,
                subagent_type=subagent_type,
                framework=None,
            )
            for role, subagent_type in CRITIC_ROSTER[mode]
        )
    return ()
```

> Note: when `CRITIC_ROSTER[mode]` is empty (light mode), `active_stages` never includes `CouncilStage.CRITIQUE`, so this branch is never reached in light mode — but returning `()` is the correct safety net.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/context/domains/test_council_batch.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/domains/council_batch.py tests/context/domains/test_council_batch.py
git commit -m "feat(council): deterministic critic roster + agent-bounded cap"
```

---

## Task 6: CLI verb `context council-batch --next`

**Files:**
- Modify: `dummyindex/context/enums.py` (add `COUNCIL_BATCH`)
- Create: `dummyindex/cli/council_batch.py`
- Modify: `dummyindex/cli/__init__.py` (import + register)
- Test: `tests/context/domains/test_council_batch_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/context/domains/test_council_batch_cli.py
import json

from dummyindex.cli import dispatch
from dummyindex.context.domains.council import append_log


def _make_feature(features_dir, feature_id, files):
    fdir = features_dir / feature_id
    fdir.mkdir(parents=True)
    (fdir / "feature.json").write_text(
        json.dumps({"feature_id": feature_id, "files": list(files)}),
        encoding="utf-8",
    )


def test_council_batch_next_json(tmp_path, capsys):
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _make_feature(features_dir, "b", ["b.py"])
    (features_dir / "INDEX.json").write_text(
        json.dumps({"features": [{"feature_id": "a"}, {"feature_id": "b"}]}),
        encoding="utf-8",
    )

    rc = dispatch(["council-batch", "--next", "--root", str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["complete"] is False
    assert payload["stage"] == 1
    assert [u["feature_id"] for u in payload["units"]] == ["a", "b"]
    assert all(u["subagent_type"] for u in payload["units"])


def test_council_batch_complete_json(tmp_path, capsys):
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    (features_dir / "INDEX.json").write_text(
        json.dumps({"features": [{"feature_id": "a"}]}), encoding="utf-8"
    )
    for stage, agent in ((1, "dev"), (4, "dev")):
        append_log(features_dir, feature_id="a", stage=stage, agent=agent, status="started")
        append_log(features_dir, feature_id="a", stage=stage, agent=agent, status="complete")

    rc = dispatch(["council-batch", "--next", "--root", str(tmp_path), "--mode", "light", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["complete"] is True
    assert payload["units"] == []


def test_council_batch_missing_features_dir_errors(tmp_path, capsys):
    rc = dispatch(["council-batch", "--next", "--root", str(tmp_path), "--json"])
    assert rc == 2
    assert "not found" in capsys.readouterr().err


def test_council_batch_bad_cap_errors(tmp_path, capsys):
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    (features_dir / "INDEX.json").write_text(
        json.dumps({"features": [{"feature_id": "a"}]}), encoding="utf-8"
    )
    rc = dispatch(["council-batch", "--next", "--root", str(tmp_path), "--cap", "0"])
    assert rc == 2
    assert "cap" in capsys.readouterr().err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/context/domains/test_council_batch_cli.py -q`
Expected: FAIL — `error: unknown context subcommand 'council-batch'` (rc 2, but the assertions on payload fail first)

- [ ] **Step 3a: Add the enum member**

In `dummyindex/context/enums.py`, after `COUNCIL_LOG = "council-log"`:

```python
    COUNCIL_BATCH = "council-batch"
```

- [ ] **Step 3b: Create the CLI module**

```python
# dummyindex/cli/council_batch.py
"""`dummyindex context council-batch --next` — the parallel-council frontier.

Wire-only: parse flags, call the `council_batch` domain, print. The council
twin of `build --next-wave`. Reads non-trivial feature ids from
`features/INDEX.json`; the JSON payload carries `complete` + the stage + one
entry per dispatch-unit (feature, role, subagent_type, framework) so the
council skill can launch a parallel Task per unit.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .common import parse_kv_flags, parse_path_and_root, resolve_context_root


def _load_feature_ids(features_dir: Path) -> list[str]:
    """Non-trivial feature ids from INDEX.json (every entry is non-trivial)."""
    index_path = features_dir / "INDEX.json"
    data = json.loads(index_path.read_text(encoding="utf-8"))
    return [f["feature_id"] for f in data.get("features", []) if f.get("feature_id")]


def run(args: list[str]) -> int:
    from dummyindex.context.domains.council_batch import CouncilMode, next_batch

    # take_positional=False: this verb has no positional path, so the *value*
    # of `--mode`/`--cap` must not be mistaken for a scope argument (matches
    # council.py). Root is passed via `--root DIR`.
    scope, explicit_root, rest = parse_path_and_root(args, take_positional=False)
    # `--next` and `--tree-enrich` and `--json` are bare flags; strip them out
    # before kv parsing so they aren't mistaken for `--key value` pairs.
    bare = {"--next", "--json", "--tree-enrich"}
    flags = {a for a in rest if a in bare}
    rest = [a for a in rest if a not in bare]
    parsed, leftover = parse_kv_flags(rest)
    if leftover:
        print(f"error: unknown argument(s) for `council-batch`: {leftover}", file=sys.stderr)
        return 2

    as_json = "--json" in flags
    tree_enrich = "--tree-enrich" in flags
    mode_raw = parsed.get("mode", "standard")
    try:
        mode = CouncilMode(mode_raw)
    except ValueError:
        print(f"error: --mode must be light|standard|deep, got {mode_raw!r}", file=sys.stderr)
        return 2
    try:
        cap = int(parsed.get("cap", "8"))
    except ValueError:
        print(f"error: --cap must be an integer, got {parsed.get('cap')!r}", file=sys.stderr)
        return 2

    repo_root = resolve_context_root(scope, explicit_root=explicit_root)
    features_dir = repo_root / ".context" / "features"
    if not (features_dir / "INDEX.json").is_file():
        print(
            f"error: {features_dir / 'INDEX.json'} not found. Run `dummyindex ingest` first.",
            file=sys.stderr,
        )
        return 2

    feature_ids = tuple(_load_feature_ids(features_dir))

    try:
        batch = next_batch(
            features_dir, repo_root, feature_ids,
            mode=mode, cap=cap, tree_enrich=tree_enrich,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if as_json:
        print(json.dumps({
            "complete": batch.complete,
            "stage": int(batch.stage) if batch.stage is not None else None,
            "mode": mode.value,
            "cap": cap,
            "units": [u.to_dict() for u in batch.units],
        }, indent=2))
        return 0

    if batch.complete:
        print("council-batch: all features complete for this mode.")
        return 0
    plural = "s" if len(batch.units) != 1 else ""
    print(
        f"council-batch: stage {int(batch.stage)} — {len(batch.units)} parallel "
        f"unit{plural} (dispatch concurrently, barrier, then re-run --next):"
    )
    for u in batch.units:
        fw = f" [{u.framework}]" if u.framework else ""
        print(f"  {u.feature_id}: {u.role} → {u.subagent_type}{fw}")
    return 0
```

- [ ] **Step 3c: Register the handler**

In `dummyindex/cli/__init__.py`, add `council_batch` to the `from . import (...)` block (alphabetically near `council`), and add to `_HANDLERS`:

```python
    ContextSubcommand.COUNCIL_BATCH: council_batch.run,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/context/domains/test_council_batch_cli.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/enums.py dummyindex/cli/council_batch.py dummyindex/cli/__init__.py tests/context/domains/test_council_batch_cli.py
git commit -m "feat(council): context council-batch --next CLI verb"
```

---

## Task 7: Document the verb in `USAGE`

**Files:**
- Modify: `dummyindex/cli/help.py`
- Test: `tests/context/domains/test_council_batch_cli.py` (add one assertion)

- [ ] **Step 1: Write the failing test**

```python
# append to tests/context/domains/test_council_batch_cli.py
from dummyindex.cli.help import USAGE


def test_usage_documents_council_batch():
    assert "council-batch" in USAGE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/context/domains/test_council_batch_cli.py::test_usage_documents_council_batch -q`
Expected: FAIL — `assert 'council-batch' in USAGE`

- [ ] **Step 3: Write minimal implementation**

In `dummyindex/cli/help.py`, immediately after the `council-log` line (near line 146-147), add:

```
  council-batch [--root DIR] --next [--mode light|standard|deep] [--cap N] [--tree-enrich] [--json]
                                    Next parallel batch of council dispatch-units
                                    (earliest incomplete stage across features).
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/context/domains/test_council_batch_cli.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dummyindex/cli/help.py tests/context/domains/test_council_batch_cli.py
git commit -m "docs(cli): document council-batch verb in USAGE"
```

---

## Task 8: Integration test — drive a multi-feature repo to completion

**Files:**
- Modify: `tests/context/domains/test_council_batch.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/context/domains/test_council_batch.py
def _complete_units(features_dir, batch):
    """Simulate every unit in a batch reaching `complete`."""
    for u in batch.units:
        _log(features_dir, u.feature_id, u.stage, u.role, "started")
        _log(features_dir, u.feature_id, u.stage, u.role, "complete")


def test_full_drive_standard_mode_reaches_complete(tmp_path):
    repo_root = tmp_path
    features_dir = repo_root / ".context" / "features"
    for fid in ("a", "b", "c"):
        _make_feature(features_dir, fid, [f"{fid}.py"])

    seen_stages = []
    for _ in range(50):  # generous guard against an infinite loop
        batch = next_batch(
            features_dir, repo_root, ("a", "b", "c"),
            mode=CouncilMode.STANDARD, cap=8, tree_enrich=False,
        )
        if batch.complete:
            break
        seen_stages.append(int(batch.stage))
        _complete_units(features_dir, batch)
    else:
        raise AssertionError("did not converge")

    assert batch.complete is True
    # standard active stages are 1,2,3,4 — each must have appeared
    assert set(seen_stages) == {1, 2, 3, 4}


def test_resume_after_partial_specify(tmp_path):
    repo_root = tmp_path
    features_dir = repo_root / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _make_feature(features_dir, "b", ["b.py"])
    # only `a` finishes specify
    _log(features_dir, "a", 1, "dev", "started")
    _log(features_dir, "a", 1, "dev", "complete")

    batch = next_batch(
        features_dir, repo_root, ("a", "b"),
        mode=CouncilMode.STANDARD, cap=8, tree_enrich=False,
    )
    # frontier is still SPECIFY, and only `b` is dispatched (a already done)
    assert batch.stage == CouncilStage.SPECIFY
    assert [u.feature_id for u in batch.units] == ["b"]
```

- [ ] **Step 2: Run test to verify it fails / passes**

Run: `uv run pytest tests/context/domains/test_council_batch.py -q`
Expected: PASS (these exercise already-built behaviour; they lock in the end-to-end contract and resumption). If `test_full_drive` fails to converge, the stage/readiness logic has a bug — fix it before continuing.

- [ ] **Step 3: (no new impl expected)**

If both pass, skip to commit. If not, debug `earliest_incomplete_stage` / `_feature_ready_for`.

- [ ] **Step 4: Commit**

```bash
git add tests/context/domains/test_council_batch.py
git commit -m "test(council): full-drive convergence + resume integration coverage"
```

---

## Task 9: Council skill markdown — retire serial loop, add parallel-dispatch procedure

No unit tests (markdown). Verify by reading.

**Files:**
- Create: `dummyindex/skills/council/22-parallel-dispatch.md`
- Modify: `dummyindex/skills/council/00-overview.md`
- Modify: `dummyindex/skills/council/19-resume.md`
- Modify: `dummyindex/skills/council/40-critique.md`
- Modify: `dummyindex/skills/skill.md`

- [ ] **Step 1: Create `22-parallel-dispatch.md`**

```markdown
# Parallel dispatch — the council batch loop

The per-feature pipeline runs **in parallel across features**, not one feature
at a time. Features are independent (each writes only to its own
`features/<id>/` tree), so the council dispatches a whole batch of agents
concurrently, waits, and advances.

## The loop

```
loop:
  batch = dummyindex context council-batch --next --cap 8 --mode <mode> [--tree-enrich] --json
  if batch.complete: break
  # dispatch ONE Task per unit in batch.units, ALL IN ONE MESSAGE, so they run concurrently:
  #   - subagent_type   = unit.subagent_type
  #   - inline the persona body: agents/dev.md (role "dev"), agents/architect.md
  #     (role "architect"), or agents/<role>.md (critics, e.g. critic-security.md)
  #   - fill {{framework}} with unit.framework for dev units
  #   - ground each agent: read spec.md / plan.md / .context/conventions/ first
  #   - each agent logs itself: council-log --feature <id> --stage <unit.stage>
  #     --agent <unit.role> --status started|complete (or failed)
  await ALL units (barrier)
repeat
```

## Stages (what the CLI returns, in order)

1 specify (dev) · 2 plan (architect) · 3 critique (critics, mode-rostered) ·
4 flow (dev) · 5 tree-enrich (dev, only when `--tree-enrich`). The CLI returns
the **earliest incomplete stage** across all features and never advances a
feature to stage N+1 until stage N is logged complete for it — so intra-feature
ordering is preserved while cross-feature work runs in parallel.

## Critic roster (deterministic, mode-gated)

- **light** — no critique stage.
- **standard** — one critic: `critic-security` (Security Engineer).
- **deep** — `critic-database` (Data Engineer), `critic-security`
  (Security Engineer), `critic-product` (general-purpose).

The CLI emits one unit per (feature, critic), so the cap bounds **agents**.

## Failure isolation

Features are independent. If one unit fails, log it
(`--status failed`), **leave that feature at its stage, and keep going** — finish
the rest of the batch and all later batches. Do **not** stop the whole council
(that is the build loop's gate, which is wrong here). At the end, **report the
features that never reached completion** so the user can re-run — a re-run
resumes exactly those, because the frontier is recomputed from the logs.

## Resumption

`--next` is stateless beyond the per-feature `_council-log.json`: it recomputes
the frontier every call. An interrupted run resumes with no special handling —
just call `--next` again.
```

- [ ] **Step 2: Edit `00-overview.md` sequencing**

In `dummyindex/skills/council/00-overview.md`, replace the Phase 2 line in the "## Sequencing" block:

Find:
```
Phase 2: Per-feature pipeline (loop over features, SEQUENTIAL per feature)
```
Replace with:
```
Phase 2: Per-feature pipeline (PARALLEL across features — see 22-parallel-dispatch.md)
   │   dispatched in stage batches via `council-batch --next`; features run
   │   concurrently, stages stay ordered per feature
```

And in the "## The pattern" intro, change the opening sentence:

Find:
```
documentation. Spec-kit-shaped: sequential, layered artifacts. One author per
layer, one artifact per step. No essay redundancy, no synthesis step.
```
Replace with:
```
documentation. Spec-kit-shaped: layered artifacts, one author per layer, one
artifact per step. Stages are ordered *within* a feature; *across* features the
pipeline runs in parallel (see 22-parallel-dispatch.md). No synthesis step.
```

- [ ] **Step 3: Edit `19-resume.md`**

Append to `dummyindex/skills/council/19-resume.md`:

```markdown

## Resumption under parallel dispatch

`council-batch --next` recomputes the earliest incomplete stage from the
per-feature logs on every call, so resuming an interrupted parallel run needs no
special handling — re-run the loop in 22-parallel-dispatch.md and it picks up at
the exact stage each feature stopped.
```

- [ ] **Step 4: Edit `40-critique.md`**

At the top of `dummyindex/skills/council/40-critique.md`, add a note aligning it to the deterministic roster (so the skill and the CLI agree):

```markdown
> **Parallel dispatch:** the critic roster is now resolved deterministically by
> mode (light = none; standard = `critic-security`; deep = database + security +
> product) — see 22-parallel-dispatch.md. The CLI emits one unit per
> (feature, critic); dispatch them in parallel with the rest of the stage-3
> batch. The mode-relevance pruning below applies only when re-running a single
> feature by hand (`--recouncil <id>`).
```

- [ ] **Step 5: Edit `skill.md` Phase 2/3 wording**

In `dummyindex/skills/skill.md`:

Find (line ~25):
```
7. **Phase 3 — Per-feature pipeline:** for each non-trivial feature, run stages 1 → 2 → 3 sequentially (specify / plan / critique — see `council/`).
```
Replace with:
```
7. **Phase 3 — Per-feature pipeline:** run stages 1 → 2 → 3 (specify / plan / critique) ordered *within* each feature, but **in parallel across features** via `context council-batch --next` — see `council/22-parallel-dispatch.md`.
```

Find (line ~221):
```
Stages run **sequentially** per feature (plan needs the dev's draft; critics need the finalised plan). Different features can be processed back-to-back.
```
Replace with:
```
Stages run **in order within a feature** (plan needs the dev's draft; critics need the finalised plan), but **different features are dispatched in parallel** — `council-batch --next` returns the earliest incomplete stage's units for up to `--cap` agents at once.
```

Find (line ~306):
```
- ❌ Don't run a feature's stages out of order — specify → plan → critique is sequential.
```
Replace with:
```
- ❌ Don't run a *single feature's* stages out of order — specify → plan → critique is ordered. (Across features, parallel is expected.)
```

- [ ] **Step 6: Verify the markdown reads correctly**

Run: `grep -n "SEQUENTIAL per feature" dummyindex/skills/council/00-overview.md dummyindex/skills/skill.md`
Expected: no matches (the serial language is gone).

- [ ] **Step 7: Commit**

```bash
git add dummyindex/skills/council/22-parallel-dispatch.md dummyindex/skills/council/00-overview.md dummyindex/skills/council/19-resume.md dummyindex/skills/council/40-critique.md dummyindex/skills/skill.md
git commit -m "docs(council): parallel-dispatch procedure; retire per-feature serial loop"
```

---

## Task 10: Version bump, CHANGELOG, full suite + coverage

**Files:**
- Modify: `pyproject.toml`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Bump version**

In `pyproject.toml`, change `version = "0.19.2"` → `version = "0.20.0"`.

- [ ] **Step 2: Add CHANGELOG entry**

Add a new section at the top of the entries in `CHANGELOG.md` (match the file's existing heading style):

```markdown
## 0.20.0

### Added
- **Parallel council dispatch.** `dummyindex context council-batch --next` — the
  council twin of `build --next-wave`. Computes the earliest incomplete stage
  across all non-trivial features and returns up to `--cap` dispatch-units so the
  council skill fans independent features out to parallel Task subagents instead
  of looping one feature at a time. Stages stay ordered within a feature; cross-
  feature work runs concurrently. Resumption is recomputed from the per-feature
  logs; failures isolate per-feature. New skill: `council/22-parallel-dispatch.md`.

### Changed
- `dev-pick` feature/manifest I/O helpers moved from the CLI into the `dev_pick`
  domain (`harvest_dep_tokens`, `read_feature_files`) so the council-batch domain
  can reuse them without crossing the layer boundary. CLI behaviour unchanged.
- Critic roster is now resolved deterministically by mode (light = none;
  standard = security; deep = database + security + product).
```

- [ ] **Step 3: Run the full suite with coverage**

Run: `uv run pytest -q --cov=dummyindex --cov-report=term-missing`
Expected: ALL pass. New modules `context/domains/council_batch.py` and
`cli/council_batch.py` at ≥ 80% coverage. No regressions in `test_dev_pick.py`,
`test_council_cli.py`, `test_build_loop.py`.

- [ ] **Step 4: Sanity-check the CLI end to end**

Run:
```bash
uv run python -m dummyindex context council-batch --next --help 2>&1 | head -3 || true
uv run python -m dummyindex context -h | grep council-batch
```
Expected: the `-h` output lists `council-batch`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml CHANGELOG.md
git commit -m "chore: release 0.20.0 — parallel council dispatch"
```

---

## Self-Review Notes (for the implementer)

- **Spec coverage:** every spec component maps to a task — domain (Tasks 1,3,4,5), CLI verb (Task 6), help (Task 7), skill docs (Task 9), version (Task 10). Acceptance items 1–7 are exercised by Tasks 4–8 + manual checks in Task 10.
- **Layering:** the domain never imports the CLI; Task 2 moves the shared I/O into the domain to keep it that way.
- **One deliberate deviation from the spec to confirm:** the spec said "cap counts agents." Tasks 4–5 honour that *at feature granularity* — a single feature's critic set is never split across batches (so a `cap` below the deep roster size still emits all 3 critics for one feature). And the **single-critic choice for standard mode is `critic-security`** — a product decision encoded here; flag it for the user.
- **No placeholders:** the only intentional staged stub is the CRITIQUE branch in Task 4, completed in Task 5; both tasks' tests pass at their own boundary.
