# Codex Guidance Specification

confidence: INFERRED

## Intent

Keep dummyindex's managed Codex instructions visible at the exact project or user-global file Codex will read, without claiming user-authored content or allowing repository configuration and symlinks to escape their trust and filesystem boundaries. The policy layer resolves Codex configuration, precedence, trust, fallback paths, and byte budgets; the output layer applies that policy to managed-block installation, preflight, ownership-aware removal, and stale-fallback cleanup.

## User-visible behavior

- Project installation selects the first existing regular instruction candidate in this order: `AGENTS.override.md`, `AGENTS.md`, then validated configured fallbacks. An existing empty file still wins; if no candidate exists, dummyindex creates `AGENTS.md` (`dummyindex/context/output/agents_md.py:110-129`, `dummyindex/context/output/agents_md.py:223-240`).
- User-global installation honors a nonempty `CODEX_HOME`, otherwise uses `<home>/.codex`; it considers only the standard instruction names and writes the managed block at the front of the selected file (`dummyindex/codex_guidance.py:29-34`, `dummyindex/context/output/agents_md.py:164-180`, `dummyindex/context/output/agents_md.py:207-220`).
- Persistent configuration overlays system, user, and trusted project-root layers. A project `.codex/config.toml` participates only when user configuration explicitly marks the resolved project root trusted; missing, unreadable, malformed, invalid, or untrusted values fall back safely (`dummyindex/codex_guidance.py:37-87`, `dummyindex/codex_guidance.py:146-181`, `dummyindex/codex_guidance.py:198-230`).
- Configured fallback names must be confined relative paths. Absolute paths, parent traversal, empty values, NULs, duplicates, and standard-name duplicates are ignored; nested candidates retain path-sensitive matching (`dummyindex/codex_guidance.py:57-67`, `dummyindex/codex_guidance.py:111-143`, `dummyindex/codex_guidance.py:233-253`).
- Before reading or writing guidance, dummyindex resolves the selected target and rejects any target outside the selected project or Codex-home scope. It also refuses project installation when the complete managed block exceeds the effective `project_doc_max_bytes` budget (`dummyindex/context/output/agents_md.py:255-270`, `dummyindex/context/output/agents_md.py:383-404`).
- Reinstallation refreshes one managed block at the front while preserving all user bytes outside it. Project blocks carry either explicit-project or user-auto-init ownership; auto-init refresh never takes ownership from an explicit project install, and selective uninstall removes only the requested owner (`dummyindex/context/output/agents_md.py:142-161`, `dummyindex/context/output/agents_md.py:349-380`, `tests/context/output/test_agents_md.py:65-122`, `tests/context/output/test_agents_md.py:773-823`).
- Uninstall inspects active names, configured fallbacks, and boundedly discovered stale fallback files. Each file fails independently: a malformed or out-of-scope target is reported while cleanup continues for safe files (`dummyindex/context/output/agents_md.py:183-204`, `dummyindex/context/output/agents_md.py:273-346`, `dummyindex/context/output/agents_md.py:407-446`).
- The project managed block includes the same always-on output policy as Claude project guidance, while the user-global Codex block omits that policy (`dummyindex/context/output/agents_md.py:33-65`, `tests/context/output/test_agents_md.py:125-151`).

## Contracts

- `codex_home(home: Path | None = None) -> Path` returns the active Codex home, preferring nonempty `CODEX_HOME` over the supplied home fallback (`dummyindex/codex_guidance.py:29-34`).
- `configured_project_doc_fallback_filenames(project_root: Path | None = None) -> tuple[str, ...]` returns the effective, ordered, deduplicated set of safe project-relative fallback paths (`dummyindex/codex_guidance.py:37-67`).
- `configured_project_doc_max_bytes(project_root: Path | None = None) -> int` returns the effective nonnegative integer budget, defaulting to 32 KiB and rejecting booleans as integer settings (`dummyindex/codex_guidance.py:25-25`, `dummyindex/codex_guidance.py:70-87`).
- `project_instruction_paths(project_root: Path | None = None) -> tuple[str, ...]` prepends standard names to configured fallbacks; `project_instruction_filenames(...) -> frozenset[str]` is its compatibility set view (`dummyindex/codex_guidance.py:90-108`).
- `is_project_instruction_path(path: str | Path, project_root: Path, *, instruction_paths: Iterable[str] | None = None) -> bool` matches candidate component suffixes inside a project and restricts outside absolute paths to basename behavior (`dummyindex/codex_guidance.py:111-143`).
- `bootstrap_project_agents_md(project_root: Path, *, owner: str = PROJECT_OWNER_EXPLICIT) -> Path` validates and writes the active project target; `preflight_project_agents_md(...) -> Path` performs the same deterministic selection and validation without writing (`dummyindex/context/output/agents_md.py:110-161`).
- `bootstrap_global_agents_md(home: Path | None = None) -> Path` writes the user-global managed block under the active Codex home (`dummyindex/context/output/agents_md.py:164-180`).
- `remove_project_agents_md(project_root: Path, *, owner: str | None = None) -> AgentsMdCleanupResult` and `remove_global_agents_md(home: Path | None = None) -> AgentsMdCleanupResult` return immutable tuples of changed paths and per-file cleanup issues rather than failing the full cleanup on one file (`dummyindex/context/output/agents_md.py:94-107`, `dummyindex/context/output/agents_md.py:183-204`, `dummyindex/context/output/agents_md.py:407-441`).
- Managed file mutation is delegated to the shared bootstrap/removal primitives with fixed begin/end markers and `place_first=True`, keeping policy decisions separate from byte-preserving block plumbing (`dummyindex/context/output/agents_md.py:24-28`, `dummyindex/context/output/agents_md.py:110-129`, `dummyindex/context/output/agents_md.py:407-441`).

## Examples

- A repository with both a nonempty `AGENTS.md` and an empty `AGENTS.override.md` receives the managed block in the override, because existence—not content—controls project precedence (`tests/context/output/test_agents_md.py:168-195`).
- A trusted project config can replace a user fallback with `PROJECT_GUIDE.md`; the same config is ignored when the user trust table marks the repository untrusted (`tests/context/output/test_agents_md.py:259-281`, `tests/context/output/test_agents_md.py:717-741`).
- A configured `docs/TEAM_GUIDE.md` that resolves through a parent symlink outside the repository is rejected without changing the external file (`tests/context/output/test_agents_md.py:239-256`).
- After fallback configuration changes, uninstall discovers the old nested managed file, removes only dummyindex's block, and leaves the team-authored text intact (`tests/context/output/test_agents_md.py:367-402`).
