# Architect notes — CLI command dispatch

## What I changed

- Collapsed ten sections to the five mandated ones (Where it lives / Architecture in three sentences / Data model / Key decisions / Open questions); boundary, patterns, and dependencies now live inside Where it lives. 277 → 211 lines.
- Deleted the "Dispatch flow" and "Default-plugin orchestration flow" step lists: each step restated a pattern or decision already in the draft. The init order is now one line with per-step ranges.
- Sharpened the boundary using `feature.json` ownership: `graph.py` → graph-query, `maintain.py`/`drift_ack.py` → maintenance, `fleet.py` → fleet, `evolve.py` → evolution, `__main__.py` → install-surface, `upgrade.py` → index-lifecycle, `default_plugins.py` → equip/install-surface. Cut the per-verb detail for those modules (graph arity/flags, maintenance-family help ranges) and kept only the one-row-plus-help-block integration fact.
- Cut `ScanEvidence`/`ScanViolationSeverity` from Where it lives: `cli/scan.py:31` imports only the latter, and neither is dispatch surface.
- Cut rebuild migration line formats and reconcile-stamp internals. `spec.md` already carries them at the user-visible level.
- Dropped the product-only open question (wire's "untrusted" label for reviewed defaults; it is already in `10-critiques.md`). Merged the init and wire exit-0 questions into one "partial outcomes" question. Folded the `maintain --help` stray-lines bullet into the registry question as evidence.
- Added two open questions found in code. First, the pre-build `resolve_depth` config read gates indexing (`dummyindex/context/domains/config.py:542-545`, `dummyindex/cli/init.py:158-165`). The draft presented `init.py:63-68` as the malformed-config path, but without `--depth` a malformed config already exits 2 before the build. Second, wire imports private `default_plugins` helpers.
- Range fixes: `dummyindex/cli/rebuild.py:39-185` → file ends at 184; `dummyindex/cli/reconcile.py:31-370` → file ends at 369 (both dropped, not re-cited); `rebuild.py:157-158` for "exits 0" → replaced by per-cause ranges; `help.py:17-715` split into template `:17-710` + `USAGE` `:715`. Several ranges in the previous `02-architect-notes.md` were stale (`enums.py:41-91`, `__init__.py:88-154`, `help.py:504-557`, `__main__.py:259-315`); they are replaced with current ones.
- Audit: every function/class named was checked against `map/symbols.json`. Module constants `_HANDLERS`, `_FLAGS_TAKING_VALUE`, `USAGE`, `_USAGE_TEMPLATE`, `_PROMPT`, `_NEWER_SCHEMA_MARKER` get 0 hits because the map indexes only functions and classes. They are cited by source `path:line` instead.
- Audit: `ContextSubcommand` has 50 members and `_HANDLERS` has 50 rows, with no gap. The count is deliberately not written into the plan, because it would drift.
- Audit, doc vs code conflict (code wins): `.context/conventions/coding-practices.md:38-39` places `ContextSubcommand` at `enums.py:40-87`, but it is at `dummyindex/context/enums.py:108-164`.
- Audit, doc evidence: `docs/COMMANDS.md`, `docs/guide/07-cli.md`, and `docs/reference/01-conventions.md` are `low` in `source-docs/INDEX.md:54,56,62`. None is cited as authority. Only the curated `.context/conventions/*.md` files are cited.
- Audit, convention conflict (code wins): "lazy-import the domain inside `run`" (`folder-organization.md:32-36`) is violated at module level by `cli/help.py:14`, `cli/config.py:13`, `cli/onboard.py:44,54`, `cli/plan_update.py:36-37`, and `cli/equip/*`. The plan records it as a convention, not an invariant.

## Patterns named

- Dispatcher: `dispatch` at `dummyindex/cli/__init__.py:148-166`.
- Registry: `_HANDLERS` at `dummyindex/cli/__init__.py:94-145`, typed `Callable[[list[str]], int]`.
- Closed alphabet as validator and registry key: `ContextSubcommand` at `dummyindex/context/enums.py:108-164`.
- Help guard (interceptor before handler): `_wants_help` at `dummyindex/cli/__init__.py:68-91`, applied at `:163-165`.
- Doc-as-data help slicing: `_USAGE_TEMPLATE` at `dummyindex/cli/help.py:17-710`, `usage_for` at `:723-765`.
- Shared parse alphabet with explicit scope: `_FLAGS_TAKING_VALUE` at `dummyindex/cli/common.py:66-93`. It has three consumers, at `__init__.py:85`, `common.py:157-166`, and `common.py:226-231`.
- Wire-only handler with lazy domain import: `dummyindex/cli/init.py:88`, `dummyindex/cli/scan.py:27-32`.
- Dual-stream rendering: `(info, warn)` → stdout/stderr at `dummyindex/cli/init.py:79-84`.
- Callable DI seam: `_PROMPT` at `dummyindex/cli/wire.py:43`, threaded through `:63,66-72`. This matches `coding-practices.md:64-67`.
- Fixed-order, fail-closed pipeline: `_wire_default_plugins_step` at `dummyindex/cli/init.py:17-84`.
- Renamed from the draft: "ordered post-build saga" became "fixed-order pipeline, fail-closed at the first gate". The code has no compensation step (`init.py:63-68` returns, nothing rolls back), so "saga" misstated the code.
- Dropped from the draft: "command-scoped application boundary". No range shows a pattern beyond one function.

## Dependencies surfaced

- Upstream: `dummyindex/__main__.py:333-348` holds the only three `dispatch` call sites (`context`, `ingest`, `status`). `_print_help` reads the alphabet at `:240-249`.
- Eager import fan-in: `dummyindex/cli/__init__.py:21-61` imports every handler module. Module-level domain imports therefore load on every invocation, including `--help`. The equip domain loads via `help.py:14`, and `context.default_plugins` via `cli/equip/install.py:20`.
- Package cycle `cli ⇄ installer`. The cli side is `cli/init.py:128`, `bootstrap.py:16`, `onboard.py:54`, `equip/dispatch.py:69`, and `check.py:199,251,346`. The installer side is `installer/install/project_init.py:56,196`. It is not an import-time cycle, because the installer side imports inside functions.
- Handler → handler edges: `check→rebuild`, `maintain→reconcile.run_stamp`, `rebuild/bootstrap/refresh→migrate`, `guard_doc_write/reconcile_gate→memory`, `statusline→plan_update`. Because of these, `rebuild.run` and `run_stamp` exit codes propagate to `check` (`dummyindex/cli/check.py:122-126`) and `maintain stamp` (`dummyindex/cli/maintain.py:392-395`).
- Cross-feature private coupling: `dummyindex/cli/wire.py:91,194,204,231` imports `_already_decided` and `_split_target` from `context.default_plugins`.
- Shared pure renderer: `format_migration_report` (`dummyindex/context/build/upgrade.py:618-665`) is consumed by `cli/rebuild.py:139-146` and by `installer/install/project_init.py:62`.
- Text coupling: `_NEWER_SCHEMA_MARKER` (`dummyindex/cli/reconcile.py:205`) depends on the `read_meta` prose at `dummyindex/context/build/meta.py:76-79`.
- No downstream cycle: `context/domains/*` never imports `cli` (`folder-organization.md:27-28`).

## Decisions promoted

- Each decision below is now written as "decided X because Y", using the rationale stated in code.
- Help wins even in a value slot. The bare-`equip` probing hazard is the reason, and the cost is a literal `--help` value (`dummyindex/cli/__init__.py:72-78,159-162`).
- Enum construction is the only verb validator. The top-level list is "derived from the enum so this list can never drift" (`dummyindex/__main__.py:241-242`). Three tests keep it aligned, not generation.
- Value flags are allowlisted per command, because `--platform codex` was once silently ignored (`dummyindex/cli/common.py:215-225`).
- `usage_error` always points at `--help`, because bare-verb probing mutated the repo for `equip` (`dummyindex/cli/common.py:49-63`).
- A curated index refuses `init` without `--force`, and a bare `rebuild` without `--full`. The reasons are taxonomy loss from a stray `ingest`, and hooks that expect a cheap refresh (`dummyindex/cli/init.py:167-182`, `dummyindex/cli/rebuild.py:107-122`). The draft had this only as a flow step.
- One-run flags (`--no-default-plugins`, `--no-superpowers`, `--depth`) are never persisted (`dummyindex/cli/init.py:24-27,90-113`, `dummyindex/cli/reconcile.py:35-37`).
- Disclosure precedes plugin mutation, because the defaults contain reviewed third-party code (`dummyindex/cli/init.py:46-49`).
- A strict config read precedes tolerant healing, so malformed state never falls back to `default_wired()`. The config is reread so that backfilled defaults apply in the same run (`dummyindex/cli/init.py:53-62`).
- Only `wire` prompts, so install and ingest never block a pipe or CI run (`dummyindex/cli/wire.py:3-8,22-26`, `help.py:665-668`).
- Approval is target-scoped, so a custom plugin never installs unrelated defaults (`dummyindex/cli/wire.py:224-229`).
- Post-build failures are warnings, not exit codes, because the index is already complete. Sources: `init.py:213-217`, `upgrade.py:533-539`, `rebuild.py:26-27`.
- A newer-schema meta means "upgrade", not "ingest" (`dummyindex/cli/reconcile.py:208-214`).
