# Preflight inventory — plan

confidence: INFERRED

## Where it lives

The domain is `dummyindex/context/domains/preflight/`: `__init__.py` (public surface, `__init__.py:14-21`), `inventory.py` (the read-only census + git probe), `models.py` (two frozen dataclasses), `ownership.py` (the `.context/` ownership enum + probe), `render.py` (markdown rendering). The CLI entry point is `dummyindex/cli/preflight.py`, wired into the dispatch table as `ContextSubcommand.PREFLIGHT -> preflight.run` (`cli/__init__.py:40,113`). The equip-adopt consumer is `dummyindex/context/domains/equip/generate/adopt.py`, which imports `PreflightReport` and reads `preflight.project_agents` to resolve specialist coverage (`adopt.py:30-31,108`); further equip callers are `cli/equip/dispatch.py` and `cli/equip/common.py`.

## Architecture in three sentences

`build_preflight_report` is a single read-only pass that delegates to four private inspectors — `_inspect_settings`, `_list_rule_files`, `_list_agent_names`, `_has_managed_block` — plus `context_ownership` and `_git_clean`, assembling one frozen `PreflightReport` (`inventory.py:28-62`). The report is pure data: rendering (`render.py`) and JSON (`models.py:to_dict`) are separate, side-effect-free projections of it, keeping the I/O at the CLI boundary (`preflight.py:31-37`). Markers it checks (`SENTINEL`, `CURRENT_CLAUDE_EVENTS`, `BEGIN_MARKER`, the `dummyindex_version` ownership key) are imported from the modules that *write* them, never re-spelled, so preflight stays in lock-step with install (`inventory.py:17-19`).

## Data model

- `SettingsState(exists, parseable, user_hook_events: tuple[str,...], dummyindex_hook_present)` — frozen; `parseable=False` means "valid JSON object absent ⇒ won't touch" (`models.py:14-29`).
- `PreflightReport(project_root, is_git_repo, git_clean, settings, rule_files, project_agents, claude_md_exists, claude_md_has_managed_block, context_exists=False, context_owned=None)` — frozen; the two `.context/` fields are additive with defaults so older direct constructions keep working (`models.py:32-46`).
- `ContextOwnership(str, Enum)` — `ABSENT` (missing/empty `.context/`, safe to create), `OURS` (`meta.json` is a JSON object carrying `dummyindex_version`), `FOREIGN` (content present without the marker, or unreadable) (`ownership.py:26-53`).
- Tri-state mappings: `_owned_flag` collapses the three-member enum into `context_owned` `None`/`True`/`False` (`inventory.py:65-74`); `git_clean` is `Optional[bool]` (`inventory.py:169-194`).

## Key decisions

- **Read-only, additive.** The domain never writes. The whole promise — "show what I'll touch before touching it" — depends on it (`inventory.py:1-7`). The report's `.context/` fields were added with defaults rather than as required args, preserving back-compat constructions (`models.py:44-46`).
- **Tolerant, never-raises probing.** `context_ownership` classifies a missing/unreadable/malformed `meta.json` in a non-empty `.context/` as FOREIGN rather than throwing (`ownership.py:9-15,64-70`). `_inspect_settings` walks an arbitrary hooks shape (nulls, non-string commands, non-list entries) without crashing (`inventory.py:103-137`). `_git_clean` returns `None` on any git failure (`inventory.py:190-194`). The conservative choice everywhere is "don't claim what can't be verified."
- **Newer-schema tolerance.** Ownership deliberately avoids the strict `read_meta` loader so an index written by a *newer* dummyindex still reads as OURS rather than raising (`ownership.py:9-15`).
- **Lock-step with install via imported markers.** `SENTINEL` / `CURRENT_CLAUDE_EVENTS` / `BEGIN_MARKER` / the `dummyindex_version` key come from their owning modules, so a change to what install writes is automatically reflected here (`inventory.py:17-19`).
- **Legacy-sentinel scrub semantics.** A sentinel under a non-current event reads as *not* installed (it will be scrubbed, not refreshed), so it must not suppress a fresh install (`inventory.py:121-127`).
- **Git read-only safety.** `git status --porcelain` runs with `GIT_OPTIONAL_LOCKS=0` so a hook killed mid-query never strands `index.lock`, including inside a submodule under the superproject's `.git/modules/` (`inventory.py:169-194`).

## Open questions

- `_list_rule_files` globs `**/*.md` (recursive) while `_list_agent_names` globs `*.md` (flat) (`inventory.py:24-25`). Intentional asymmetry (nested rule trees vs flat agents) or an inconsistency? Code wins; worth confirming against install's actual layout.
- `_inspect_settings` records `user_hook_events` but the renderer only surfaces them as a leave-untouched line; no warning is raised when a user hook collides with the SessionStart event dummyindex installs into. Whether collision visibility belongs here or in install is unsettled.
- The MEDIUM-confidence docs touching this domain (`docs.md`) carry many broken refs and predate the current `.context/`-ownership fields; they are historical, not authoritative for the current contract.
