# Preflight inventory — plan

confidence: INFERRED

## Bounded context

The domain answers one question — *"what will dummyindex touch in this repo, and what must it leave alone?"* — as pure data, before any write. It owns three probes and nothing else: a read-only census of `.claude/`, an ownership verdict on an existing `.context/`, and a git-clean check. It writes nothing, decides nothing, and renders nothing with side effects; the running `/dummyindex` session (Phase 0) and equip/adopt are the deciders downstream.

Everything lives under `dummyindex/context/domains/preflight/`:

- `inventory.py` — the read-only census + git probe; `build_preflight_report` is the entry point (`inventory.py:28-62`).
- `models.py` — two frozen, data-only dataclasses with `to_dict()` (`models.py:15-60`).
- `ownership.py` — the `.context/` ownership enum + tolerant probe (`ownership.py:26-70`).
- `render.py` — markdown projection of the report (`render.py:27-65`).
- `__init__.py` — public surface re-export (`__init__.py:14-21`).

I/O sits only at the CLI boundary: `dummyindex/cli/preflight.py` resolves args, calls `build_preflight_report`, and prints markdown or JSON (`preflight.py:17-37`), wired into the dispatch table as `ContextSubcommand.PREFLIGHT -> preflight.run` (`cli/__init__.py:40,113`).

## Patterns named

- **Single read-only pass, fan-out to private inspectors.** `build_preflight_report` does one resolve-and-assemble pass, delegating to four private census functions — `_inspect_settings` (`inventory.py:77`), `_list_rule_files` (`inventory.py:140`), `_list_agent_names` (`inventory.py:155`), `_has_managed_block` (`inventory.py:162`) — plus `context_ownership` and `_git_clean`, then constructs one frozen `PreflightReport` (`inventory.py:28-62`). No inspector writes; each returns a value.
- **Report-as-pure-data; rendering and JSON are projections.** `render_preflight_md` (`render.py:27-65`) and `PreflightReport.to_dict` (`models.py:48-60`, nesting `SettingsState.to_dict` at `models.py:23-29`) are side-effect-free reads of the same frozen record. This follows the repo's frozen-dataclass + hand-written-`to_dict` convention (`conventions/coding-practices.md`) and keeps I/O at the boundary (`conventions/data-access.md`).
- **Tri-state collapse of the ownership enum.** `_owned_flag` maps the three-member `ContextOwnership` onto `context_owned` `None`/`True`/`False` (`inventory.py:65-74`); `git_clean` is the parallel `Optional[bool]` from `_git_clean` (`inventory.py:169-194`). `None` means "nothing to own / can't verify," never "false."
- **Lock-step markers, imported never re-spelled.** `SENTINEL`, `CURRENT_CLAUDE_EVENTS`, `BEGIN_MARKER`, and the `dummyindex_version` ownership key are imported from the modules that *write* them (`inventory.py:17-19`; `_OWNERSHIP_MARKER` in `ownership.py:1-7`), so a change to what install writes is reflected here automatically.
- **Tolerant, never-raises probing.** `context_ownership` classifies a missing/unreadable/malformed `meta.json` in a non-empty `.context/` as FOREIGN instead of throwing (`ownership.py:34-53,64-70`); `_inspect_settings` walks an arbitrary hooks shape — nulls, non-string commands, non-list entries — without crashing (`inventory.py:103-137`); `_git_clean` returns `None` on any git failure (`inventory.py:190-194`).

## Data model

- `SettingsState(exists, parseable, user_hook_events: tuple[str,...], dummyindex_hook_present)` — frozen; `parseable=False` means "no valid JSON object ⇒ won't touch" (`models.py:15-29`).
- `PreflightReport(project_root, is_git_repo, git_clean, settings, rule_files, project_agents, claude_md_exists, claude_md_has_managed_block, context_exists=False, context_owned=None)` — frozen; collection fields are tuples per convention (`models.py:33-60`).
- `ContextOwnership(str, Enum)` — `ABSENT` (missing/empty `.context/`, safe to create), `OURS` (`meta.json` is a JSON object carrying `dummyindex_version`), `FOREIGN` (content without the marker, or unreadable) (`ownership.py:26-31`).

## Dependencies surfaced

**Consumes** (imports markers, must stay in lock-step):
- `dummyindex.context.hooks` — `SENTINEL`, `CURRENT_CLAUDE_EVENTS` (`inventory.py:17`).
- `dummyindex.context.output.bootstrap` — `BEGIN_MARKER` (`inventory.py:18`).
- `dummyindex.pipeline.io` — `is_git_repo`, which accepts a `.git` *file* for submodules/worktrees (`inventory.py:19,45`).

**Consumed by** — `PreflightReport` is this domain's exported contract; downstream callers read `preflight.project_agents` to drive adoption:
- **equip/adopt** — `resolve_coverage(*, preflight, …)` (`adopt.py:81-144`) splits requested capabilities into generate-vs-adopt off `preflight.project_agents` via `_project_specs` (`adopt.py:108,162-178`); `adopt_existing` is the back-compat thin wrapper (`adopt.py:147-159`). Import at `adopt.py:31`.
- **equip CLI** — `cli/equip/common.py:203-206` and `cli/equip/dispatch.py:68,278-286` call `build_preflight_report` and type on `PreflightReport`.
- **the `/dummyindex` skill, Phase 0** — runs `dummyindex context preflight <root>` before any write and is told to *honor its warnings* (`~/.claude/skills/dummyindex/SKILL.md:21,110-138`). Preflight is read-only/additive to that flow — it reports, it never blocks.

## Decisions promoted

- **Read-only, additive — because the whole promise is "show what I'll touch before touching it."** The domain never writes (`inventory.py:1-7`). The two `.context/` fields (`context_exists`, `context_owned`) were added with defaults rather than required args **so older direct `PreflightReport` constructions keep working** (`models.py:33-46`).
- **Never-raises probing — because a preflight that crashes can't preflight.** The conservative rule throughout is "don't claim what can't be verified": unreadable ownership ⇒ FOREIGN (`ownership.py:64-70`), weird hook shapes ⇒ no crash (`inventory.py:103-137`), git failure ⇒ `None` (`inventory.py:190-194`).
- **Newer-schema tolerance — because a `.context/` written by a newer dummyindex is still ours.** Ownership deliberately avoids the strict `read_meta` loader, which raises on a higher `schema_version`, so such an index reads as OURS not FOREIGN (`ownership.py:9-15`).
- **Legacy-sentinel scrub semantics — because a stale sentinel must not suppress a fresh install.** A sentinel under a non-current event reads as *not* installed (`dummyindex_hook_present=False`): it will be scrubbed, not refreshed (`inventory.py:121-137`).
- **Git read-only safety — because a hook killed mid-query must not strand `index.lock`.** `git status --porcelain` runs with `GIT_OPTIONAL_LOCKS=0`, including inside a submodule under the superproject's `.git/modules/` (`inventory.py:169-194`).

## Open questions

- **Rule/agent glob asymmetry.** `_list_rule_files` globs `**/*.md` (recursive) while `_list_agent_names` globs `*.md` (flat) (`inventory.py:140-160`). Likely intentional — nested rule trees vs flat agents — but worth confirming against install's actual layout. Code wins.
- **Hook-collision visibility.** `_inspect_settings` records `user_hook_events`, but the renderer only surfaces them as a leave-untouched line (`render.py`); no warning fires when a user hook shares the SessionStart event dummyindex installs into. Whether that warning belongs here or in install is unsettled.
