# Preflight inventory — spec

confidence: INFERRED

## Intent

Take a read-only census of the repo's existing Claude Code setup *before* dummyindex writes. This lets the running `/dummyindex` session show "what I will touch vs leave alone". It also lets the session refuse to clobber a config it doesn't understand. The domain touches nothing. It reads `.claude/`, probes `.context/` ownership, and queries git (`inventory.py:1-7`). Second job: feed equip/adopt. Project agents it inventories drive specialist adoption (`adopt.py:1-24`).

The domain answers three questions deterministically:

- Which `.claude/` artifacts exist, and whether they carry dummyindex's own markers.
- Whether an existing `.context/` is dummyindex's to manage or a foreign tool's (hands off).
- Whether the working tree is clean enough that writes stay git-reversible.

## User-visible behavior

`dummyindex context preflight [path] [--root DIR] [--json]` (`preflight.py:17-37`). Prints markdown by default, JSON with `--json`. An unknown trailing flag prints `error: unknown argument(s)` to stderr and returns exit 2 (`preflight.py:26-28`). The markdown report (`render.py:27-65`) has four sections:

- **Will write / manage** — `.context/**`, `.claude/CLAUDE.md` (managed block only), `.claude/settings.json` (one additive SessionStart hook) (`render.py:21-24,68-73`). If `.context/` is foreign, the `.context/**` line is replaced by a WITHHELD notice (`render.py:17-20,70-72`).
- **Will leave untouched** — rule files under `.claude/rules/`, project agents under `.claude/agents/`. Also untouched: every source file and prose doc in the repo. The user's own hooks: the events carrying them, or "none found" (`render.py:40-51`). Lists truncate after 8 items with a `+N more` suffix (`render.py:113-117`).
- **⚠ Warnings** (only when non-empty, `render.py:53-57,76-104`). Foreign `.context/` (remedy `mv .context .context.other`), unparseable `settings.json`, dirty working tree, undeterminable git status, not-a-git-repo.
- **State** — one line each for `.context` (absent/empty/owned/foreign), `CLAUDE.md` (absent/managed-block-present/plain), `settings.json` (absent/unparseable/hook-present/plain), and git (not-a-repo/unknown/clean/dirty) (`render.py:59-63,120-154`).

The JSON form is `report.to_dict()` (`models.py:48-60`), with nested `settings` via `SettingsState.to_dict()` (`models.py:23-29`).

## Contracts

Public surface re-exported from the domain package (`__init__.py:14-21`):

- `build_preflight_report(project_root: Path) -> PreflightReport` (`inventory.py:28-62`) — the read-only inventory entry point. Inspects `settings.json`, lists rules/agents, checks `CLAUDE.md` for a managed block. Queries git clean-state (only if a git repo). Probes `.context/` ownership.
- `render_preflight_md(report: PreflightReport) -> str` (`render.py:27-65`) — markdown summary.
- `context_ownership(context_dir: Path) -> ContextOwnership` (`ownership.py:34-53`) — classifies a `.context/` path as `ABSENT` / `OURS` / `FOREIGN`; never raises (`ownership.py:46`).
- `class ContextOwnership(str, Enum)` with members `ABSENT` / `OURS` / `FOREIGN` (`ownership.py:26-31`).
- `@dataclass(frozen=True) PreflightReport` (`models.py:32-60`) — fields `project_root`, `is_git_repo`, `git_clean: Optional[bool]`, `settings: SettingsState`, `rule_files`, `project_agents`, `claude_md_exists`, `claude_md_has_managed_block`, `context_exists=False`, `context_owned: Optional[bool]=None`; `to_dict()`.
- `@dataclass(frozen=True) SettingsState` (`models.py:14-29`) — fields `exists`, `parseable`, `user_hook_events`, `dummyindex_hook_present`; `to_dict()`.

Equip-facing consumers:

- `resolve_coverage(*, preflight, proposal_capabilities=(), forced_capabilities=(), templated_capabilities=frozenset(), stack_frontend=True) -> Coverage` (`adopt.py:81-144`) — splits requested capabilities into generate-vs-adopt using `preflight.project_agents`. `stack_frontend=False` skips FRONTEND templates and registry adoption, not project agents (`adopt.py:130-143`).
- `adopt_existing(*, preflight, needed) -> tuple[AdoptSpec, ...]` (`adopt.py:147-159`) — back-compat wrapper: pure adoption, no templates.

`context_owned` is `None` (absent/empty), `True` (OURS), `False` (FOREIGN), mapped from the ownership probe by `_owned_flag` (`inventory.py:65-74`). `git_clean` is `None` when not a git repo or git is unavailable/failed (`inventory.py:169-194`).

## Examples

- **Empty repo** — no `.claude/`, no `.context/`, git repo with clean tree. Report shows `.context` "absent — will be created", `settings.json` "absent", `CLAUDE.md` "absent", git "clean". No warnings.
- **Foreign `.context/`** — a `.context/` with content but no `meta.json` carrying `dummyindex_version`. `context_ownership` returns `FOREIGN` (`ownership.py:51-53`). The managed-paths line becomes WITHHELD. A warning advises moving it aside (`render.py:78-85`).
- **Newer-schema `.context/`** — `meta.json` written by a newer dummyindex (higher `schema_version`) still reads as OURS. The probe deliberately does *not* reuse the strict `read_meta` loader, which would raise (`ownership.py:9-15,64-70`).
- **Settings with mixed hooks** — `_inspect_settings` tolerates any JSON shape without crashing. Inputs include nulls, non-string commands, non-list values, `ownership` of weird hook shapes. It records `user_hook_events` for non-dummyindex hooks. It sets `dummyindex_hook_present` only when the sentinel sits under a *current* event, not a legacy one (`inventory.py:103-137`).
- **Submodule / worktree** — `is_git_repo` accepts a `.git` *file* (submodule/worktree). `_git_clean` runs with `GIT_OPTIONAL_LOCKS=0`, so a killed hook never strands `index.lock` (`inventory.py:45,169-194`).
